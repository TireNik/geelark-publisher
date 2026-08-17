"""Stop GeeLark cloud phones when publisher tasks no longer need them."""
from django.utils import timezone

from publisher.models import PublicationTask
from publisher.utils import check_phone_status, stop_cloud_phone

ACTIVE_PHONE_STATUSES = ('sending', 'submitted', 'processing', 'stopping')


def profile_has_active_task(profile_id, exclude_id=None) -> bool:
    query = PublicationTask.objects.filter(
        profile_id=str(profile_id),
        status__in=ACTIVE_PHONE_STATUSES,
    )
    if exclude_id is not None:
        query = query.exclude(id=exclude_id)
    return query.exists()


def stop_phone_if_idle(profile_id, exclude_task_id=None) -> bool:
    """Stop the cloud phone when no other publisher task still needs it."""
    if not profile_id:
        return False
    if profile_has_active_task(profile_id, exclude_task_id):
        return False
    try:
        status = check_phone_status(str(profile_id))
        if not status.get('is_running'):
            return False
    except Exception:
        pass
    try:
        return bool(stop_cloud_phone(str(profile_id)))
    except Exception as exc:
        print(f"Не удалось остановить телефон {profile_id}: {exc}")
        return False


def mark_phone_stopped(profile_id, when=None) -> int:
    when = when or timezone.now()
    return PublicationTask.objects.filter(
        profile_id=str(profile_id),
        geelark_started_at__isnull=False,
        phone_stopped_at__isnull=True,
    ).update(phone_stopped_at=when)


def reap_idle_phones() -> int:
    """Stop phones left running after success/error (no active task on profile)."""
    stopped = 0
    profile_ids = (
        PublicationTask.objects.filter(
            geelark_started_at__isnull=False,
            phone_stopped_at__isnull=True,
            status__in=('success', 'error'),
        )
        .values_list('profile_id', flat=True)
        .distinct()
    )
    now = timezone.now()
    for profile_id in profile_ids:
        if stop_phone_if_idle(profile_id):
            mark_phone_stopped(profile_id, now)
            stopped += 1
    return stopped
