"""
Сессионный воркер с экономией минут GeeLark.

Совместим с upstream feature/scheduled-phone-timeout:
- телефоны НЕ стартуем здесь (отложенный старт + geelark_watchdog);
- после API create → status=submitted (+ sync/watchdog доводят до success/error);
- refresh_session_status вместо принудительного completed.

Фазы:
1) prepare — download + PUT storage (без телефона), локальный файл сразу удаляем;
   один URL → один resourceUrl (дедуп для YT+TT).
2) publish — только create RPA task (параллельно до GEELARK_MAX_PARALLEL).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from config import settings
from django.db import close_old_connections
from django.utils import timezone

from . import utils as u
from .models import PublicationTask, UploadSession, refresh_session_status

logger = logging.getLogger(__name__)


def _cfg_int(name: str, default: int) -> int:
    return int(getattr(settings, name, default))


def _safe_remove(path: Optional[str]) -> None:
    if not path:
        return
    try:
        if os.path.isfile(path):
            os.remove(path)
            print(f"Удалён temp: {path}")
    except OSError as exc:
        print(f"Не удалось удалить {path}: {exc}")


def _mark_error(task: PublicationTask, message: str, t0: float) -> None:
    close_old_connections()
    try:
        task.refresh_from_db()
    except Exception:
        pass
    task.status = "error"
    task.error_message = (message or "error")[:4000]
    task.attempt_count = (task.attempt_count or 0) + 1
    task.processed_at = timezone.now()
    task.t_total_ms = int((time.monotonic() - t0) * 1000)
    task.save()


def _prepare_url(video_url: str, session_id: int, sample_task_id: int, sla_deadline: float) -> Dict:
    """Скачать URL один раз, залить в storage, удалить локальный файл. Без телефона."""
    close_old_connections()
    if time.monotonic() > sla_deadline:
        raise TimeoutError("SLA: prepare не уложился")

    save_path = os.path.join(
        settings.TEMP_VIDEO_DIR,
        f"prep_{session_id}_{sample_task_id}_{abs(hash(video_url)) % 10_000_000}.mp4",
    )
    os.makedirs(settings.TEMP_VIDEO_DIR, exist_ok=True)
    timeout = _cfg_int("GEELARK_DOWNLOAD_TIMEOUT_SEC", 180)

    try:
        t_dl0 = time.monotonic()
        if u.is_yandex_disk_url(video_url):
            direct = u.get_yandex_direct_download_url(video_url)
            u._stream_download_to_file(direct, save_path, timeout=timeout)
        elif u.is_direct_http_video_url(video_url):
            u._stream_download_to_file(video_url, save_path, timeout=timeout)
        else:
            raise ValueError(f"Неподдерживаемый URL: {video_url}")

        t_download_ms = int((time.monotonic() - t_dl0) * 1000)
        file_size = os.path.getsize(save_path)

        if time.monotonic() > sla_deadline:
            raise TimeoutError("SLA: upload storage не начат вовремя")

        t_up0 = time.monotonic()
        resource_url = u.upload_local_file_to_geelark_storage(save_path)
        t_upload_ms = int((time.monotonic() - t_up0) * 1000)

        return {
            "resource_url": resource_url,
            "file_size_bytes": file_size,
            "t_download_ms": t_download_ms,
            "t_upload_storage_ms": t_upload_ms,
        }
    finally:
        _safe_remove(save_path)


def _publish_task(
    task: PublicationTask,
    prepared: Dict,
    publish_semaphore: threading.Semaphore,
    sla_deadline: float,
) -> None:
    """Сохраняет подготовленное видео без запуска телефона GeeLark."""
    close_old_connections()
    t0 = time.monotonic()

    try:
        # Сразу выявляем неверный ID профиля, но GeeLark-задачу пока не создаём.
        u.validate_profile_id(task.profile_id)

        task.status = "prepared"
        task.file_size_bytes = prepared.get("file_size_bytes")
        task.t_download_ms = prepared.get("t_download_ms")
        task.t_upload_storage_ms = prepared.get("t_upload_storage_ms")
        task.resource_url = prepared.get("resource_url") or ""
        task.t_total_ms = int((time.monotonic() - t0) * 1000)
        task.error_message = ""

        task.save(
            update_fields=[
                "status",
                "file_size_bytes",
                "t_download_ms",
                "t_upload_storage_ms",
                "resource_url",
                "t_total_ms",
                "error_message",
            ]
        )
        print(f"✓ task {task.id} prepared; GeeLark will start near publish time")
    except Exception as exc:
        _mark_error(task, str(exc), t0)
        print(f"✗ task {task.id}: {exc}")
    finally:
        close_old_connections()


def session_worker(session_id: int) -> None:
    """Prepare (parallel, no phone) → publish API (parallel, без старта телефонов)."""
    close_old_connections()
    session = UploadSession.objects.get(id=session_id)
    session.status = "processing"
    session.save(update_fields=["status"])

    tasks = list(session.tasks.filter(status="pending").order_by("id"))
    if not tasks:
        refresh_session_status(session)
        print(f"Сессия {session_id}: нет pending задач")
        return

    max_parallel = max(1, min(3, _cfg_int("GEELARK_MAX_PARALLEL", 3)))
    sla_sec = _cfg_int("GEELARK_TASK_SLA_SEC", 900)

    url_to_tasks: Dict[str, List[PublicationTask]] = defaultdict(list)
    for task in tasks:
        url_to_tasks[str(task.video_url)].append(task)

    prepared_by_url: Dict[str, Dict] = {}

    def prepare_one(video_url: str, samples: List[PublicationTask]) -> None:
        close_old_connections()
        for t in samples:
            t.status = "downloading"
            t.save(update_fields=["status"])
        t0 = time.monotonic()
        try:
            prepared_by_url[video_url] = _prepare_url(
                video_url,
                session_id=session_id,
                sample_task_id=samples[0].id,
                sla_deadline=time.monotonic() + sla_sec,
            )
            print(
                f"prepare OK url={video_url[:80]}… "
                f"size={prepared_by_url[video_url]['file_size_bytes']}"
            )
        except Exception as exc:
            print(f"prepare FAIL url={video_url[:80]}…: {exc}")
            for t in samples:
                _mark_error(t, f"prepare: {exc}", t0)

    print(f"Сессия {session_id}: prepare {len(url_to_tasks)} URL, parallel={max_parallel}")
    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        futs = [
            pool.submit(prepare_one, url, samples)
            for url, samples in url_to_tasks.items()
        ]
        for fut in as_completed(futs):
            fut.result()

    close_old_connections()
    pending_publish = list(
        PublicationTask.objects.filter(
            session_id=session_id,
            status="downloading",
            video_url__in=list(prepared_by_url.keys()),
        ).order_by("id")
    )

    publish_semaphore = threading.Semaphore(max_parallel)
    print(f"Сессия {session_id}: publish {len(pending_publish)} задач, parallel={max_parallel}")

    try:
        with ThreadPoolExecutor(max_workers=max_parallel) as pool:
            futs = [
                pool.submit(
                    _publish_task,
                    task,
                    prepared_by_url[str(task.video_url)],
                    publish_semaphore,
                    time.monotonic() + sla_sec,
                )
                for task in pending_publish
            ]
            for fut in as_completed(futs):
                try:
                    fut.result()
                except Exception as exc:
                    logger.exception("publish future crashed: %s", exc)
    finally:
        try:
            temp_dir = settings.TEMP_VIDEO_DIR
            if os.path.isdir(temp_dir):
                prefix = f"prep_{session_id}_"
                for name in os.listdir(temp_dir):
                    if name.startswith(prefix):
                        _safe_remove(os.path.join(temp_dir, name))
        except OSError:
            pass

    close_old_connections()
    session.refresh_from_db()
    refresh_session_status(session)
    print(f"Сессия ID:{session.id} завершена (отправка в GeeLark); RPA может ещё идти")
