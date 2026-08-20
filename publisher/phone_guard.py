"""Stop GeeLark cloud phones when publisher tasks no longer need them."""
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from publisher.models import PublicationTask
from publisher.utils import check_phone_status, stop_cloud_phone

# RPA already created or running — phone must stay on.
RUNNING_PHONE_STATUSES = ('sending', 'submitted', 'processing', 'stopping')
# Prepared for dispatch; keep the phone only if publish_time is due soon
# (same-device YT+TT), not for a task scheduled hours later.
QUEUED_PHONE_STATUSES = ('pending', 'downloading', 'prepared')


def dispatch_lead_seconds() -> int:
    return max(0, int(getattr(settings, 'GEELARK_DISPATCH_LEAD_SECONDS', 120)))


def sibling_keeps_phone(task, *, now, lead_seconds, exclude_id=None) -> bool:
    """True if this sibling means we must not stop the cloud phone yet."""
    if exclude_id is not None and getattr(task, 'id', None) == exclude_id:
        return False
    status = getattr(task, 'status', '') or ''
    if status in RUNNING_PHONE_STATUSES:
        return True
    if status not in QUEUED_PHONE_STATUSES:
        return False
    when = getattr(task, 'publish_time', None)
    if when is None:
        return True
    return when <= now + timedelta(seconds=int(lead_seconds))


def profile_has_running_rpa(profile_id, exclude_id=None) -> bool:
    """True while this env already has a GeeLark RPA in flight.

    Dispatch uses this so a second network waits instead of overlapping
    youtubePubShort / task/add on one cloud phone.
    """
    if not profile_id:
        return False
    query = PublicationTask.objects.filter(
        profile_id=str(profile_id),
        status__in=RUNNING_PHONE_STATUSES,
    )
    if exclude_id is not None:
        query = query.exclude(id=exclude_id)
    return query.exists()


def profile_has_active_task(profile_id, exclude_id=None, now=None) -> bool:
    """True while this env still has RPA in flight or another network due now.

    Excel and Video Farm ingest share session_worker; both create one
    PublicationTask per network on the same profile_id. After YouTube
    succeeds, TikTok is often still `prepared` — keep the phone on so we
    do not pay a second boot.
    """
    if not profile_id:
        return False
    now = now or timezone.now()
    soon = now + timedelta(seconds=dispatch_lead_seconds())
    due_queue = Q(status__in=QUEUED_PHONE_STATUSES) & Q(publish_time__lte=soon)
    query = PublicationTask.objects.filter(profile_id=str(profile_id)).filter(
        Q(status__in=RUNNING_PHONE_STATUSES) | due_queue
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
