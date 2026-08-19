"""Cut wasted mobile-proxy traffic after GeeLark publish failures."""
from __future__ import annotations

from typing import Optional

from django.conf import settings
from django.utils import timezone

from publisher.models import PublicationTask, refresh_session_status
from publisher.phone_guard import mark_phone_stopped, stop_phone_if_idle
from publisher.utils import cancel_geelark_task, rotate_geelark_proxy_port

PROXY_FAIL_CODE = '29996'
NOT_LOGGED_IN_CODE = '20116'
ABORTABLE_STATUSES = (
    'pending',
    'downloading',
    'sending',
    'prepared',
    'submitted',
    'processing',
)


def proxy_fail_abort_threshold() -> int:
    return max(1, int(getattr(settings, 'GEELARK_PROXY_FAIL_ABORT_THRESHOLD', 3)))


def should_abort_session(proxy_fail_count, threshold=None) -> bool:
    limit = proxy_fail_abort_threshold() if threshold is None else int(threshold)
    return int(proxy_fail_count) >= limit


def skip_dispatch_reason(profile_id, fail_pairs, threshold=None) -> Optional[str]:
    """Return a skip reason if creating another GeeLark task would waste proxy.

    fail_pairs: iterable of (fail_code, profile_id) for the same session.
    """
    pairs = [(str(code), str(pid)) if pid is not None else (str(code), '') for code, pid in fail_pairs]
    proxy_n = sum(1 for code, _pid in pairs if code == PROXY_FAIL_CODE)
    if should_abort_session(proxy_n, threshold):
        return (
            f'Сессия остановлена: {proxy_n} отказов прокси ({PROXY_FAIL_CODE}).'
        )
    profile = str(profile_id)
    for code, pid in pairs:
        if pid != profile:
            continue
        if code == NOT_LOGGED_IN_CODE:
            return f'Аккаунт на телефоне не авторизован ({NOT_LOGGED_IN_CODE}).'
        if code == PROXY_FAIL_CODE:
            return f'На этом телефоне уже был отказ прокси ({PROXY_FAIL_CODE}).'
    return None


def remaining_task_ids(tasks, exclude_id=None, profile_id=None):
    profile = None if profile_id is None else str(profile_id)
    ids = []
    for task in tasks:
        if exclude_id is not None and task.id == exclude_id:
            continue
        if getattr(task, 'status', None) not in ABORTABLE_STATUSES:
            continue
        if profile is not None and str(getattr(task, 'profile_id', '')) != profile:
            continue
        ids.append(task.id)
    return ids


def abort_remaining_tasks(session, *, reason, exclude_id=None, profile_id=None, now=None) -> int:
    """Cancel leftover session work so phones are not kept on a dead proxy/account."""
    now = now or timezone.now()
    query = session.tasks.filter(status__in=ABORTABLE_STATUSES)
    if exclude_id is not None:
        query = query.exclude(id=exclude_id)
    if profile_id is not None:
        query = query.filter(profile_id=str(profile_id))

    aborted = 0
    phones = []
    for task in query:
        geelark_id = getattr(task, 'geelark_task_id', '') or ''
        if geelark_id:
            try:
                cancel_geelark_task(geelark_id)
            except Exception as exc:
                print(f'Не удалось отменить GeeLark task {geelark_id}: {exc}')
        task.status = 'error'
        task.error_message = (reason or 'Отменено для экономии прокси.')[:4000]
        task.processed_at = now
        update_fields = ['status', 'error_message', 'processed_at']
        task.save(update_fields=update_fields)
        if task.profile_id:
            phones.append(task.profile_id)
        aborted += 1

    seen = set()
    for phone in phones:
        if phone in seen:
            continue
        seen.add(phone)
        try:
            if stop_phone_if_idle(phone, exclude_task_id=exclude_id):
                mark_phone_stopped(phone, now)
        except Exception as exc:
            print(f'Не удалось остановить телефон {phone} после abort: {exc}')

    refresh_session_status(session)
    return aborted


def apply_fail_side_effects(task, when, proxy_rotation_results) -> str:
    """Stop phones and drop leftover work after 29996 / 20116. Rotate only with phone off."""
    fail = str(getattr(task, 'geelark_fail_code', '') or '')
    if fail not in {PROXY_FAIL_CODE, NOT_LOGGED_IN_CODE}:
        return ''

    session = task.session
    profile = str(task.profile_id)
    notes = []

    if fail == PROXY_FAIL_CODE:
        aborted = abort_remaining_tasks(
            session,
            reason=f'Отменено: на этом телефоне уже был отказ прокси ({PROXY_FAIL_CODE}).',
            exclude_id=task.id,
            profile_id=profile,
            now=when,
        )
        if aborted:
            notes.append(f'Снято задач с этого телефона: {aborted}.')
        if stop_phone_if_idle(profile, exclude_task_id=task.id):
            if hasattr(task, 'phone_stopped_at'):
                task.phone_stopped_at = when
            mark_phone_stopped(profile, when)
        if profile not in proxy_rotation_results:
            proxy_rotation_results[profile] = rotate_geelark_proxy_port(profile)
        rotate = proxy_rotation_results.get(profile) or {}
        if rotate.get('message'):
            notes.append(rotate['message'])

        already = set(
            PublicationTask.objects.filter(
                session=session,
                geelark_fail_code=int(PROXY_FAIL_CODE),
            ).values_list('id', flat=True)
        )
        already.add(task.id)
        if should_abort_session(len(already)):
            aborted_session = abort_remaining_tasks(
                session,
                reason=(
                    f'Сессия остановлена: {len(already)} отказов прокси '
                    f'({PROXY_FAIL_CODE}).'
                ),
                exclude_id=task.id,
                now=when,
            )
            if aborted_session:
                notes.append(f'Сессия снята, задач: {aborted_session}.')

    elif fail == NOT_LOGGED_IN_CODE:
        aborted = abort_remaining_tasks(
            session,
            reason=f'Отменено: аккаунт на телефоне не авторизован ({NOT_LOGGED_IN_CODE}).',
            exclude_id=task.id,
            profile_id=profile,
            now=when,
        )
        if aborted:
            notes.append(f'Снято задач с этого телефона: {aborted}.')

    return ' '.join(notes)
