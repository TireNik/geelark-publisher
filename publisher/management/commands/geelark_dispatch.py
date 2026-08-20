from datetime import timedelta
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from publisher import utils as u
from publisher.cost_guard import skip_dispatch_reason
from publisher.models import PublicationTask, refresh_session_status
from publisher.phone_guard import profile_has_running_rpa


class Command(BaseCommand):
    help = "Создаёт задачи GeeLark только незадолго до времени публикации."

    def handle(self, *args, **options):
        now = timezone.now()
        lead_seconds = max(0, int(settings.GEELARK_DISPATCH_LEAD_SECONDS))
        dispatch_before = now + timedelta(seconds=lead_seconds)

        task_ids = list(
            PublicationTask.objects.filter(
                status="prepared",
                publish_time__isnull=False,
                publish_time__lte=dispatch_before,
            )
            .order_by("publish_time", "id")
            .values_list("id", flat=True)
        )

        submitted = 0
        failed = 0
        deferred = 0

        for task_id in task_ids:
            with transaction.atomic():
                task = (
                    PublicationTask.objects.select_for_update()
                    .select_related("session")
                    .get(pk=task_id)
                )

                if task.status != "prepared":
                    continue

                fail_pairs = list(
                    task.session.tasks.exclude(geelark_fail_code=None).values_list(
                        "geelark_fail_code", "profile_id"
                    )
                )
                skip_reason = skip_dispatch_reason(task.profile_id, fail_pairs)
                if skip_reason:
                    task.status = "error"
                    task.error_message = f"GeeLark: {skip_reason}"
                    task.processed_at = now
                    task.save(update_fields=["status", "error_message", "processed_at"])
                    refresh_session_status(task.session)
                    failed += 1
                    self.stderr.write(f"Задача {task.id}: пропуск — {skip_reason}")
                    continue

                if profile_has_running_rpa(task.profile_id, exclude_id=task.id):
                    deferred += 1
                    self.stdout.write(
                        f"Задача {task.id}: ждём, на телефоне {task.profile_id} уже идёт RPA."
                    )
                    continue

                task.status = "sending"
                task.save(update_fields=["status"])

            started = time.monotonic()

            try:
                if not task.resource_url:
                    raise ValueError("Подготовленное видео отсутствует в хранилище GeeLark.")

                env_id = u.validate_profile_id(task.profile_id)

                geelark_task_id = u.create_geelark_publish_task(
                    env_id=env_id,
                    resource_url=task.resource_url,
                    title=task.title,
                    comment=task.comment,
                    publish_time=task.publish_time,
                    social_network=task.social_network,
                )

                task.status = "submitted"
                task.geelark_task_id = str(geelark_task_id)
                task.t_create_task_ms = int((time.monotonic() - started) * 1000)
                task.attempt_count = (task.attempt_count or 0) + 1
                task.processed_at = timezone.now()
                task.error_message = ""

                task.save(
                    update_fields=[
                        "status",
                        "geelark_task_id",
                        "t_create_task_ms",
                        "attempt_count",
                        "processed_at",
                        "error_message",
                    ]
                )

                refresh_session_status(task.session)
                submitted += 1
                self.stdout.write(f"Задача {task.id}: отправлена в GeeLark.")

            except Exception as exc:
                task.status = "error"
                task.error_message = f"GeeLark: {exc}"
                task.t_create_task_ms = int((time.monotonic() - started) * 1000)
                task.processed_at = timezone.now()

                task.save(
                    update_fields=[
                        "status",
                        "error_message",
                        "t_create_task_ms",
                        "processed_at",
                    ]
                )

                refresh_session_status(task.session)
                failed += 1
                self.stderr.write(f"Задача {task.id}: ошибка — {exc}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Отложенная отправка завершена: отправлено {submitted}, "
                f"отложено {deferred}, ошибок {failed}."
            )
        )