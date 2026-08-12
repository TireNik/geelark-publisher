from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from publisher.models import PublicationTask, UploadSession, refresh_session_status
from publisher.utils import cancel_geelark_task, stop_cloud_phone
from publisher.views import sync_geelark_statuses


class Command(BaseCommand):
    help = 'Cancels GeeLark tasks exceeding the time limit and stops their phones.'

    def handle(self, *args, **options):
        sessions = list(
            UploadSession.objects.filter(
                tasks__status__in=['processing', 'stopping']
            ).distinct()
        )

        if sessions:
            sync_geelark_statuses(sessions, force=True)

        now = timezone.now()
        timeout = timedelta(minutes=settings.GEELARK_TASK_TIMEOUT_MINUTES)
        deadline = now - timeout

        stopped = 0
        for task in PublicationTask.objects.filter(
            status='stopping',
            geelark_status__in=[3, 4, 7],
        ):
            another_task_is_active = PublicationTask.objects.filter(
                profile_id=task.profile_id,
                status__in=['submitted', 'processing'],
            ).exclude(id=task.id).exists()

            if another_task_is_active:
                continue

            try:
                phone_stopped = stop_cloud_phone(task.profile_id)
            except Exception:
                phone_stopped = False

            if not phone_stopped:
                continue

            task.processed_at = now
            if task.geelark_status == 3:
                task.status = 'success'
                task.error_message = ''
                task.geelark_fail_code = None
                task.save(update_fields=[
                    'status', 'error_message', 'geelark_fail_code', 'processed_at'
                ])
            else:
                task.status = 'error'
                if not task.error_message:
                    task.error_message = 'GeeLark: задача отменена после превышения 15 минут.'
                task.save(update_fields=['status', 'error_message', 'processed_at'])
            stopped += 1

        cancelled = 0
        overdue = PublicationTask.objects.filter(
            status='processing',
            geelark_started_at__isnull=False,
            geelark_started_at__lte=deadline,
        )

        for task in overdue:
            try:
                was_cancelled = cancel_geelark_task(task.geelark_task_id)
            except Exception:
                was_cancelled = False

            if not was_cancelled:
                continue

            task.status = 'stopping'
            task.geelark_cancel_requested_at = now
            task.error_message = (
                f'GeeLark: публикация не завершилась за '
                f'{settings.GEELARK_TASK_TIMEOUT_MINUTES} минут; запрошена отмена.'
            )
            task.save(update_fields=[
                'status', 'geelark_cancel_requested_at', 'error_message'
            ])
            cancelled += 1

        for session in sessions:
            refresh_session_status(session)

        self.stdout.write(
            self.style.SUCCESS(
                f'роверка завершена: отменено {cancelled}, остановлено телефонов {stopped}.'
            )
        )
