"""ADB push of a local mp4 into the cloud-phone gallery (Stage C).

Does not use phone/uploadFile (that re-downloads the URL through PAYG).
Requires `adb` on the publisher host and GeeLark ADB enabled on the profile.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import requests
from django.conf import settings

from publisher.utils import _geelark_api_post, check_phone_status, start_cloud_phone

logger = logging.getLogger(__name__)

GALLERY_REMOTE_PATH = "/sdcard/Download/vf_publish.mp4"


def youtube_gallery_mode_enabled() -> bool:
    mode = str(getattr(settings, "GEELARK_YOUTUBE_PUBLISH_MODE", "stock") or "stock")
    return mode.strip().lower() == "gallery"


def _adb_bin() -> str:
    return str(getattr(settings, "GEELARK_ADB_BIN", "adb") or "adb")


def _boot_wait_sec() -> int:
    return max(5, int(getattr(settings, "GEELARK_ADB_BOOT_WAIT_SEC", 45)))


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


def enable_adb(env_id: str) -> None:
    result = _geelark_api_post("/adb/setStatus", {"ids": [str(env_id)], "open": True})
    if result.get("code") != 0:
        raise RuntimeError(f"ADB enable failed: {result.get('msg') or result}")


def get_adb_endpoint(env_id: str, attempts: int = 8) -> dict:
    last_error = "ADB getData returned no endpoint"
    for attempt in range(max(1, attempts)):
        result = _geelark_api_post("/adb/getData", {"ids": [str(env_id)]})
        if result.get("code") != 0:
            last_error = f"ADB getData failed: {result.get('msg') or result}"
        else:
            items = (result.get("data") or {}).get("items") or []
            for item in items:
                if str(item.get("id")) != str(env_id):
                    continue
                if item.get("code") not in (0, None):
                    last_error = f"ADB endpoint code {item.get('code')}"
                    break
                ip = item.get("ip") or ""
                port = str(item.get("port") or "")
                pwd = item.get("pwd") or ""
                if ip and port and pwd:
                    return {"ip": ip, "port": port, "pwd": pwd, "serial": f"{ip}:{port}"}
                last_error = "ADB endpoint missing ip/port/pwd"
                break
        time.sleep(2 if attempt + 1 < attempts else 0)
    raise RuntimeError(last_error)


def _run_adb(args: list[str], timeout: int = 120, redact: str = "") -> subprocess.CompletedProcess:
    cmd = [_adb_bin(), *args]
    completed = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        shown = " ".join(args)
        if redact:
            shown = shown.replace(redact, "***")
        err = (completed.stderr or completed.stdout or "").strip()[:400]
        if redact:
            err = err.replace(redact, "***")
        raise RuntimeError(f"adb {shown} failed: {err}")
    return completed


def connect_and_login(endpoint: dict) -> None:
    serial = endpoint["serial"]
    pwd = endpoint["pwd"]
    connected = _run_adb(["connect", serial], timeout=30)
    out = f"{connected.stdout or ''} {connected.stderr or ''}".lower()
    if "failed" in out and "already connected" not in out:
        raise RuntimeError(f"adb connect {serial} failed")
    _run_adb(["-s", serial, "shell", "glogin", pwd], timeout=30, redact=pwd)


def download_resource(resource_url: str) -> Path:
    suffix = Path(resource_url.split("?", 1)[0]).suffix or ".mp4"
    handle = tempfile.NamedTemporaryFile(prefix="vf-adb-", suffix=suffix, delete=False)
    handle.close()
    path = Path(handle.name)
    timeout = int(getattr(settings, "GEELARK_DOWNLOAD_TIMEOUT_SEC", 180))
    with requests.get(resource_url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        with path.open("wb") as out:
            shutil.copyfileobj(response.raw, out)
    return path


def push_to_gallery(serial: str, local_path: Path) -> str:
    remote = GALLERY_REMOTE_PATH
    _run_adb(["-s", serial, "push", str(local_path), remote], timeout=180)
    _run_adb(
        [
            "-s",
            serial,
            "shell",
            "am",
            "broadcast",
            "-a",
            "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
            "-d",
            f"file://{remote}",
        ],
        timeout=30,
    )
    return remote


def push_resource_url_to_gallery(env_id: str, resource_url: str) -> str:
    """Start phone, enable ADB, push mp4 into Download. Returns remote path."""
    ensure_phone_running(str(env_id))
    enable_adb(str(env_id))
    endpoint = get_adb_endpoint(str(env_id))
    connect_and_login(endpoint)
    local = download_resource(resource_url)
    try:
        return push_to_gallery(endpoint["serial"], local)
    finally:
        try:
            os.unlink(local)
        except OSError:
            pass
