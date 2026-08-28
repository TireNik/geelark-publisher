"""Put an OSS mp4 into the cloud-phone Downloads folder (OpenAPI only).

Uses POST /phone/uploadFile + /phone/uploadFile/result. No local adb, no
phone/uploadFile alternatives that need extra packages. Files land in
Downloads; optional /shell/execute scans them into the gallery.
"""
from __future__ import annotations

import logging
import threading
import time

from django.conf import settings

from publisher.utils import _geelark_api_post, check_phone_status, start_cloud_phone

logger = logging.getLogger(__name__)

GALLERY_REMOTE_PATH = "/sdcard/Download/"
_UPLOAD_SUCCESS = {1, 3}
_UPLOAD_FAIL = {4, 5, 7}
_push_lock = threading.Lock()
_pushed: dict[tuple[str, str], str] = {}


def gallery_publish_mode_enabled() -> bool:
    """Opt-in. Default is stock youtubePubShort / task/add (working path of 24.08)."""
    raw = (
        getattr(settings, "GEELARK_PUBLISH_MODE", None)
        or getattr(settings, "GEELARK_YOUTUBE_PUBLISH_MODE", None)
        or "stock"
    )
    return str(raw).strip().lower() == "gallery"


def youtube_gallery_mode_enabled() -> bool:
    return gallery_publish_mode_enabled()


def reset_gallery_push_cache() -> None:
    with _push_lock:
        _pushed.clear()


def _boot_wait_sec() -> int:
    return max(5, int(getattr(settings, "GEELARK_PHONE_BOOT_WAIT_SEC", 45)))


def _upload_wait_sec() -> int:
    return max(15, int(getattr(settings, "GEELARK_UPLOAD_TIMEOUT_SEC", 180)))


def ensure_phone_running(env_id: str) -> None:
    """Start the cloud phone if needed and wait until status=Started."""
    try:
        info = check_phone_status(env_id)
        if info.get("is_running"):
            return
    except Exception:
        logger.info("Phone status unknown for %s, trying start", env_id)

    try:
        start_cloud_phone(str(env_id))
    except Exception as exc:
        try:
            if check_phone_status(env_id).get("is_running"):
                return
        except Exception:
            pass
        raise RuntimeError(f"phone start failed: {exc}") from exc

    deadline = time.time() + _boot_wait_sec()
    while time.time() < deadline:
        info = check_phone_status(env_id)
        if info.get("is_running"):
            time.sleep(3)
            return
        time.sleep(2)
    raise RuntimeError(f"Cloud phone {env_id} did not reach Started")


def _wait_upload_file_result(task_id: str) -> None:
    deadline = time.time() + _upload_wait_sec()
    last = "no result yet"
    while time.time() < deadline:
        result = _geelark_api_post("/phone/uploadFile/result", {"taskId": str(task_id)})
        if result.get("code") != 0:
            last = f"uploadFile/result: {result.get('msg') or result}"
            time.sleep(2)
            continue
        status = (result.get("data") or {}).get("status")
        last = f"status={status}"
        try:
            code = int(status)
        except (TypeError, ValueError):
            code = None
        if code in _UPLOAD_FAIL:
            raise RuntimeError(f"phone/uploadFile failed ({last})")
        if code in _UPLOAD_SUCCESS:
            return
        time.sleep(2)
    raise RuntimeError(f"phone/uploadFile timed out ({last})")


def _scan_downloads(env_id: str) -> None:
    """Best-effort gallery index. Shell is official OpenAPI; skip if the phone rejects it."""
    try:
        result = _geelark_api_post(
            "/shell/execute",
            {
                "id": str(env_id),
                "cmd": (
                    "am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE "
                    "-d file:///sdcard/Download/"
                ),
            },
        )
        if result.get("code") != 0:
            logger.info("media scan skipped: %s", result.get("msg") or result)
    except Exception as exc:
        logger.info("media scan skipped: %s", exc)


def upload_resource_url_to_phone(env_id: str, resource_url: str) -> str:
    """Start phone and copy OSS URL into Downloads via OpenAPI. Returns remote dir."""
    ensure_phone_running(str(env_id))
    result = _geelark_api_post(
        "/phone/uploadFile",
        {"id": str(env_id), "fileUrl": str(resource_url)},
    )
    if result.get("code") != 0:
        raise RuntimeError(f"phone/uploadFile failed: {result.get('msg') or result}")
    task_id = (result.get("data") or {}).get("taskId")
    if not task_id:
        raise RuntimeError("phone/uploadFile returned no taskId")
    _wait_upload_file_result(str(task_id))
    _scan_downloads(str(env_id))
    return GALLERY_REMOTE_PATH


def ensure_resource_on_gallery(env_id: str, resource_url: str) -> str:
    """One uploadFile per (envId, resourceUrl) for the process lifetime."""
    key = (str(env_id), str(resource_url))
    with _push_lock:
        cached = _pushed.get(key)
    if cached:
        logger.info("gallery already has file on %s", env_id)
        return cached
    remote = upload_resource_url_to_phone(env_id, resource_url)
    with _push_lock:
        _pushed[key] = remote
    return remote


# Names used by the previous ADB path.
push_resource_url_to_gallery = ensure_resource_on_gallery
