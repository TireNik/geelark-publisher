import threading

from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib import messages
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser

from .models import UploadSession, PublicationTask, Document
from .forms import ExcelUploadForm
from .utils import parse_excel_file, session_worker, parse_publish_time, convert_social_networks
from .serializers import UploadSessionSerializer, PublicationTaskSerializer
from datetime import datetime


# HTML СТРАНИЦЫ (только шаблоны)

@ensure_csrf_cookie
def upload_page(request):
    """
    Страница загрузки файла.
    Только отдает HTML, все данные через API.
    """
    return render(request, 'publisher/upload.html')


def status_page(request, session_id):
    """
    Страница статуса.
    Только отдает HTML с session_id, данные подтянутся через API.
    """
    context = {
        'session_id': session_id
    }
    return render(request, 'publisher/status.html', context)


# API ENDPOINTS (для данных)


class ExcelUploadView(APIView):
    """ APIView-класс загрузки Excel-файла """
    parser_classes = (MultiPartParser,)

    def post(self, request):
        excel_file = request.FILES.get('excel_file')

        if not excel_file:
            return Response({
                'error': 'Файл не предоставлен'
            }, status=status.HTTP_400_BAD_REQUEST)
        # Проверка расширения
        if not excel_file.name.endswith(('.xlsx', '.xls')):
            return Response({
                'error': 'Файл должен быть Excel (.xlsx или .xls)'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 1. Сохраняем документ
        document = Document.objects.create(
            file=excel_file,
            filename=excel_file.name,
        )

        # 2. Создаем сессию
        session = UploadSession.objects.create(
            name=f'Сессия от {datetime.now().strftime("%d.%m.%Y %H:%M")} - {excel_file.name}',
            document=document,
            status='pending',
        )

        # 3. Парсим Excel и создаем задачи
        try:
            rows, errors = parse_excel_file(excel_file)
            print(f'спарсили excel, смотрим:')
            print(rows)
            tasks = []
            # Создаем задачи на выполнение
            for row in rows:
                tasks.append(PublicationTask(
                    session=session,
                    profile_id=row['profile_id'],
                    social_network=row['social_network'],
                    video_url=row['video_url'],
                    title=row['title'],
                    comment=row['comment'],
                    publish_time=row['publish_time'],
                ))

            # Создаем ошибочные задачи
            for err in errors:
                err_data = err['data']
                error_message = '; '.join(err['errors'])

                # В Excel пустые обязательные ячейки приходят как None.
                # Ошибочная задача всё равно должна быть сохранена, чтобы
                # пользователь увидел номер строки и причину ошибки, но
                # поля модели не могут содержать NULL.
                profile_id = err_data.get('profile_id') or '?'
                social_network = err_data.get('social_network') or '?'
                video_url = err_data.get('video_url') or ''
                comment = err_data.get('comment') or ''

                tasks.append(PublicationTask(
                    session=session,
                    profile_id=str(profile_id),
                    social_network=str(social_network),
                    video_url=str(video_url),
                    title=str(err_data.get('youtube_title') or comment)[:255],
                    comment=str(comment),
                    publish_time=datetime.now(), #timezone.now(),
                    status='error',
                    error_message=error_message
                ))

            print(f'tasks???')
            print(tasks)
            PublicationTask.objects.bulk_create(tasks)

            # 3. Запускаем фоновую обработку (threading)
            thread = threading.Thread(
                target=session_worker,
                args=(session.id,),
                daemon=False  # Не убивать при перезапуске Django
            )
            thread.start()

            # 4. Отвечаем сразу, не дожидаясь обработки
            response_data = {
                'success': True,
                'session_id': session.id,
                'total_tasks': len(tasks),
                'message': f'Файл загружен. Создано {len(tasks)} задач. Обработка началась.',
                'status_url': f'/status/{session.id}/'
            }

            return Response(response_data, status=status.HTTP_201_CREATED)

        except Exception as e:
            # Если ошибка - помечаем сессию как failed
            session.status = 'failed'
            session.save()
            document.status = 'failed'
            document.save()

            return Response({
                'success': False,
                'error': str(e),
                'message': f'Ошибка при обработке файла: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)



class TaskStatusAPIView(APIView):
    """
    APIView-класс для вывода прогресса задач.
    Возвращает статус сессии и список задач.
    """

    def get(self, request, session_id):
        session = get_object_or_404(UploadSession, id=session_id)
        tasks = session.tasks.all()

        # Считаем прогресс
        if session.total_tasks > 0:
            progress = (session.submitted_tasks + session.success_tasks + session.error_tasks) / session.total_tasks * 100
        else:
            progress = 0

        # Сериализуем данные
        session_data = UploadSessionSerializer(session).data
        tasks_data = PublicationTaskSerializer(tasks, many=True).data

        return Response({
            'session': session_data,
            'tasks': tasks_data,
            'progress': round(progress, 1),
            'stats': {
                'total': session.total_tasks,
                'success': session.success_tasks,
                'submitted': session.submitted_tasks,
                'error': session.error_tasks,
                'pending': session.total_tasks - session.submitted_tasks - session.success_tasks - session.error_tasks
            }
        })


class SessionsListAPIView(APIView):
    """API для получения списка всех сессий"""

    def get(self, request):
        sessions = UploadSession.objects.all().order_by('-uploaded_at')[:30]

        sessions_data = []
        for session in sessions:
            data = {
                'id': session.id,
                'name': session.name,
                'file_name': session.file_name if hasattr(session, 'file_name') else None,
                'uploaded_at': session.uploaded_at,
                'status': session.status,
                'status_display': session.get_status_display(),
                'total_tasks': session.total_tasks,
                'success_tasks': session.success_tasks,
                'error_tasks': session.error_tasks,
                'progress_percent': round((session.success_tasks + session.error_tasks) / session.total_tasks * 100, 1) if session.total_tasks > 0 else 0
            }
            sessions_data.append(data)

        return Response({
            'success': True,
            'sessions': sessions_data
        })
