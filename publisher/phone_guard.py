"""Stop GeeLark cloud phones when publisher tasks no longer need them."""
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from publisher.models import PublicationTask, refresh_session_status
from publisher.utils import check_phone_status, stop_cloud_phone

# RPA already created or running — phone must stay on.
RUNNING_PHONE_STATUSES = ('sending', 'submitted', 'processing', 'stopping')
# Prepared for dispatch; keep the phone only if publish_time is due soon
# (same-device YT+TT), not for a task scheduled hours later.
QUEUED_PHONE_STATUSES = ('pending', 'downloading', 'prepared')


def dispatch_lead_seconds() -> int:
    return max(0, int(getattr(settings, 'GEELARK_DISPATCH_LEAD_SECONDS', 120)))


def max_parallel_jobs() -> int:
    """Cap simultaneous GeeLark phones / OSS prepares (default 2)."""
    return max(1, int(getattr(settings, 'GEELARK_MAX_PARALLEL', 2)))


def sending_zombie_seconds() -> int:
    """Grace for status=sending before create_geelark_publish_task returns."""
    return max(60, int(getattr(settings, 'GEELARK_SENDING_ZOMBIE_SECONDS', 600)))


def sibling_keeps_phone(task, *, now, lead_seconds, exclude_id=None) -> bool:
    """True if this sibling means we must not stop the cloud phone yet."""
    if exclude_id is not None and getattr(task, 'id', None) == exclude_id:
        return False
    status = getattr(task, 'status', '') or ''
    if status in RUNNING_PHONE_STATUSES:
        return not is_zombie_running_task(task, now=now)
    if status not in QUEUED_PHONE_STATUSES:
        return False
    when = getattr(task, 'publish_time', None)
    if when is None:
        return True
    return when <= now + timedelta(seconds=int(lead_seconds))


def is_zombie_running_task(task, now=None) -> bool:
    """True for stuck sending/submitted without a GeeLark task id past grace.

    Dispatch sets status=sending and stamps processed_at, then calls GeeLark.
    If that call never finishes (or an old row stays sending forever), the row
    must not block the whole profile forever.
    """
    now = now or timezone.now()
    status = getattr(task, 'status', '') or ''
    if status not in ('sending', 'submitted'):
        return False
    gid = (getattr(task, 'geelark_task_id', None) or '').strip()
    if gid:
        return False
    anchor = getattr(task, 'processed_at', None)
    if anchor is None:
        # Legacy zombies never stamped processed_at when entering sending.
        return True
    return anchor <= now - timedelta(seconds=sending_zombie_seconds())


def _live_running_rpa_q(now=None):
    """ORM filter: statuses that truly occupy the cloud phone."""
    now = now or timezone.now()
    grace = now - timedelta(seconds=sending_zombie_seconds())
    has_geelark_id = ~Q(geelark_task_id='') & Q(geelark_task_id__isnull=False)
    fresh_sending = Q(status='sending', processed_at__gte=grace)
    return (Q(status__in=RUNNING_PHONE_STATUSES) & has_geelark_id) | fresh_sending


def profile_has_running_rpa(profile_id, exclude_id=None, now=None) -> bool:
    """True while this env already has a GeeLark RPA in flight.

    Dispatch uses this so a second network waits instead of overlapping
    youtubePubShort / task/add on one cloud phone.

    Ignores zombie ``sending``/``submitted`` rows without ``geelark_task_id``
    (stuck mid-create or abandoned months ago).
    """
    if not profile_id:
        return False
    now = now or timezone.now()
    query = PublicationTask.objects.filter(
        profile_id=str(profile_id),
    ).filter(_live_running_rpa_q(now))
    if exclude_id is not None:
        query = query.exclude(id=exclude_id)
    return query.exists()


def running_rpa_count(exclude_id=None, now=None) -> int:
    """How many GeeLark phones are actually in flight (all profiles)."""
    now = now or timezone.now()
    query = PublicationTask.objects.filter(_live_running_rpa_q(now))
    if exclude_id is not None:
        query = query.exclude(id=exclude_id)
    return query.count()


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
        _live_running_rpa_q(now) | due_queue
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


def reap_zombie_running_tasks(now=None) -> int:
    """Mark stuck sending/submitted without GeeLark id as error so dispatch unblocks."""
    now = now or timezone.now()
    grace = now - timedelta(seconds=sending_zombie_seconds())
    zombies = list(
        PublicationTask.objects.filter(
            status__in=('sending', 'submitted'),
        )
        .filter(Q(geelark_task_id='') | Q(geelark_task_id__isnull=True))
        .filter(Q(processed_at__isnull=True) | Q(processed_at__lt=grace))
        .select_related('session')
    )
    reaped = 0
    sessions = set()
    for task in zombies:
        task.status = 'error'
        task.error_message = (
            'GeeLark: зомби sending/submitted без task id — снято с блокировки телефона.'
        )
        task.processed_at = now
        task.save(update_fields=['status', 'error_message', 'processed_at'])
        sessions.add(task.session_id)
        reaped += 1
    for session_id in sessions:
        session = next(
            (t.session for t in zombies if t.session_id == session_id),
            None,
        )
        if session is not None:
            refresh_session_status(session)
    return reaped
