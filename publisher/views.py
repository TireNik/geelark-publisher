import threading
from datetime import datetime, timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib import messages
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser

from .models import UploadSession, PublicationTask, Document, refresh_session_status
from .forms import ExcelUploadForm
from .utils import (
    parse_excel_file,
    session_worker,
    parse_publish_time,
    convert_social_networks,
    query_geelark_task_statuses,
)
from .serializers import UploadSessionSerializer, PublicationTaskSerializer


# HTML СТРАНИЦЫ (только шаблоны)

@ensure_csrf_cookie
def upload_page(request):
    """
    Страница загрузки файла.
    Только отдает HTML, все данные через API.
    """
    return render(request, 'publisher/upload.html')


@ensure_csrf_cookie
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
        # Обычное обновление страницы также незаметно сверяет незавершённые
        # задачи с GeeLark. Ошибка внешнего API не должна скрывать уже
        # сохранённые статусы пользователя.
        try:
            sync_geelark_statuses([session])
        except Exception:
            pass
        return Response(build_session_status_payload(session))


def build_session_status_payload(session):
    """Формирует данные статуса с прогрессом финальных результатов GeeLark."""
    tasks = session.tasks.all()
    if session.total_tasks > 0:
        progress = (session.success_tasks + session.error_tasks) / session.total_tasks * 100
    else:
        progress = 0

    return {
        'session': UploadSessionSerializer(session).data,
        'tasks': PublicationTaskSerializer(tasks, many=True).data,
        'progress': round(progress, 1),
        'stats': {
            'total': session.total_tasks,
            'success': session.success_tasks,
            'submitted': session.submitted_tasks,
            'in_progress': session.in_progress_tasks,
            'error': session.error_tasks,
            'pending': session.tasks.filter(
                status__in=['pending', 'downloading', 'sending']
            ).count(),
        },
    }


def sync_geelark_statuses(sessions, force=False):
    """Синхронизирует незавершённые задачи нескольких сессий с GeeLark.

    При обычном просмотре не обращаемся к GeeLark по одной и той же задаче
    чаще раза в 20 секунд. Ручная кнопка использует force=True.
    """
    sessions = list(sessions)
    if not sessions:
        return {'checked': 0, 'updated': 0, 'not_returned': 0}

    tasks = list(
        PublicationTask.objects.filter(session__in=sessions)
        .exclude(geelark_task_id='')
        .exclude(status__in=['success', 'error'])
    )
    if not force:
        refresh_after = timezone.now() - timedelta(seconds=20)
        tasks = [
            task for task in tasks
            if task.geelark_checked_at is None or task.geelark_checked_at <= refresh_after
        ]

    checked_at = timezone.now()
    updated = 0
    not_returned = 0
    status_names = {
        1: 'ожидает запуска',
        2: 'выполняется',
        3: 'завершено',
        4: 'завершилось с ошибкой',
        7: 'отменено',
    }

    if tasks:
        external_tasks = query_geelark_task_statuses(
            [task.geelark_task_id for task in tasks]
        )

        for task in tasks:
            external = external_tasks.get(task.geelark_task_id)
            if not external:
                not_returned += 1
                continue

            try:
                external_status = int(external.get('status'))
            except (TypeError, ValueError):
                continue

            task.geelark_status = external_status
            task.geelark_checked_at = checked_at
            update_fields = ['geelark_status', 'geelark_checked_at']

            if external_status == 1:
                task.status = 'submitted'
                task.error_message = ''
                update_fields.extend(['status', 'error_message'])
            elif external_status == 2:
                task.status = 'processing'
                task.error_message = ''
                update_fields.extend(['status', 'error_message'])
            elif external_status == 3:
                task.status = 'success'
                task.error_message = ''
                task.geelark_fail_code = None
                task.processed_at = checked_at
                update_fields.extend(['status', 'error_message', 'geelark_fail_code', 'processed_at'])
            elif external_status in (4, 7):
                task.status = 'error'
                task.geelark_fail_code = external.get('failCode')
                reason = external.get('failDesc') or status_names[external_status]
                task.error_message = (
                    f"GeeLark: {reason}"
                    + (f" (код {task.geelark_fail_code})" if task.geelark_fail_code else '')
                )
                task.processed_at = checked_at
                update_fields.extend([
                    'status', 'geelark_fail_code', 'error_message', 'processed_at'
                ])
            else:
                continue

            task.save(update_fields=update_fields)
            updated += 1

    for session in sessions:
        refresh_session_status(session)

    return {
        'checked': len(tasks),
        'updated': updated,
        'not_returned': not_returned,
    }


class GeeLarkTaskStatusSyncAPIView(APIView):
    """Ручная принудительная сверка сохранённых ID задач с GeeLark."""

    def post(self, request, session_id):
        session = get_object_or_404(UploadSession, id=session_id)

        try:
            sync = sync_geelark_statuses([session], force=True)
        except Exception as exc:
            return Response(
                {'error': f'Не удалось получить статусы из GeeLark: {exc}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response({
            'message': 'Статусы GeeLark обновлены.',
            'sync': sync,
            **build_session_status_payload(session),
        })


class SessionsListAPIView(APIView):
    """API для получения списка всех сессий"""

    def get(self, request):
        sessions = list(UploadSession.objects.all().order_by('-uploaded_at')[:30])

        # Главная страница сама актуализирует статусы видимых сессий.
        # Если GeeLark временно недоступен, пользователю всё равно отдаётся
        # последняя сохранённая информация.
        try:
            sync_geelark_statuses(sessions)
        except Exception:
            pass

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
                'submitted_tasks': session.submitted_tasks,
                'success_tasks': session.success_tasks,
                'error_tasks': session.error_tasks,
                'progress_percent': round(
                    (session.success_tasks + session.error_tasks)
                    / session.total_tasks * 100,
                    1
                ) if session.total_tasks > 0 else 0
            }
            sessions_data.append(data)

        return Response({
            'success': True,
            'sessions': sessions_data
        })
