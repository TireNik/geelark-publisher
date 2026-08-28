"""Import and run a custom YouTube Shorts gallery flow (Stage C).

Stock youtubePubShort downloads resourceUrl on the phone and skips failed
«Upload Short» clicks. This flow expects the file already in the gallery
(ADB push) and uses errorType=stop so a missing Next/Upload fails the task.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from django.conf import settings

from publisher.gallery_adb import push_resource_url_to_gallery
from publisher.utils import _geelark_api_post

logger = logging.getLogger(__name__)

FLOW_TITLE = "VF YouTube gallery Short"
FLOW_CACHE = Path("/app/data/youtube_gallery_flow_id.txt")


def _step_wait(ms: int) -> dict:
    return {
        "type": "waitTime",
        "config": {
            "remark": "",
            "timeout": ms,
            "timeoutMax": ms,
            "timeoutMin": ms,
            "timeoutType": "fixedValue",
        },
    }


def _step_click_text(text: str, search_ms: int = 8000) -> dict:
    return {
        "type": "click",
        "config": {
            "filters": [{"content": text, "type": "text"}],
            "remark": "",
            "searchTime": search_ms,
            "serial": 1,
            "serialMax": 50,
            "serialMin": 1,
            "serialType": "fixedValue",
            "variable": "",
        },
    }


def _step_wait_ele(text: str, search_ms: int = 15000, variable: str = "") -> dict:
    return {
        "type": "waitEle",
        "config": {
            "filters": [{"content": text, "type": "text"}],
            "remark": "",
            "searchTime": search_ms,
            "serial": 1,
            "serialMax": 50,
            "serialMin": 1,
            "serialType": "fixedValue",
            "variable": variable,
        },
    }


def _step_input_variable(placeholder: str, variable: str, search_ms: int = 8000) -> dict:
    return {
        "type": "input",
        "config": {
            "filters": [{"content": placeholder, "type": "text"}],
            "remark": "",
            "searchTime": search_ms,
            "serial": 1,
            "serialMax": 50,
            "serialMin": 1,
            "serialType": "fixedValue",
            "variable": variable,
        },
    }


def build_youtube_gallery_flow() -> dict:
    """English YouTube app: gallery already has vf_publish.mp4.

    Linear fail-not-skip path. Optional labels are omitted: a missing
    waitEle with errorType=stop would abort the whole task.
    No 2-minute idle after a failed click.
    """
    contents = [
        {
            "type": "openApp",
            "config": {
                "packgename": "com.google.android.youtube",
                "remark": "",
                "timeout": 30000,
            },
        },
        _step_wait(4000),
        _step_click_text("Create"),
        _step_wait(2000),
        _step_click_text("Create a short"),
        _step_wait(3000),
        _step_click_text("Gallery"),
        _step_wait(2500),
        _step_wait_ele("Next", search_ms=20000),
        _step_click_text("Next", search_ms=20000),
        _step_wait(2000),
        _step_wait_ele("Next", search_ms=20000),
        _step_click_text("Next", search_ms=20000),
        _step_wait(2000),
        _step_input_variable("Add a title that's more than 4 characters", "Title"),
        _step_wait(1000),
        _step_wait_ele("Upload Short", search_ms=30000),
        _step_click_text("Upload Short", search_ms=15000),
        _step_wait_ele("Uploaded to Your Videos", search_ms=60000),
        {
            "type": "closeApp",
            "config": {
                "packgename": "com.google.android.youtube",
                "remark": "",
                "timeout": 15000,
            },
        },
    ]
    return {
        "content": {
            "contents": contents,
            "errorType": "stop",
            "isDebug": False,
            "timeOut": "8",
            "contentType": "phone",
        },
        "desc": "Video Farm: YouTube Short from gallery, fail if Next/Upload Short missing",
        "title": FLOW_TITLE,
    }


def _flow_cache_path() -> Path:
    raw = str(getattr(settings, "GEELARK_YOUTUBE_GALLERY_FLOW_CACHE", "") or "").strip()
    return Path(raw) if raw else FLOW_CACHE


def _cached_flow_id() -> str:
    configured = str(getattr(settings, "GEELARK_YOUTUBE_GALLERY_FLOW_ID", "") or "").strip()
    if configured:
        return configured
    cache = _flow_cache_path()
    try:
        if cache.is_file():
            return cache.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return ""


def ensure_youtube_gallery_flow_id() -> str:
    existing = _cached_flow_id()
    configured = str(getattr(settings, "GEELARK_YOUTUBE_GALLERY_FLOW_ID", "") or "").strip()
    if configured:
        return configured
    payload = {"gal": json.dumps(build_youtube_gallery_flow(), ensure_ascii=False)}
    if existing:
        payload["id"] = existing
    result = _geelark_api_post("/task/flow/import", payload)
    if result.get("code") != 0:
        raise RuntimeError(f"flow import failed: {result.get('msg') or result}")
    flow_id = str((result.get("data") or {}).get("id") or existing)
    if not flow_id:
        raise RuntimeError("flow import returned no id")
    cache = _flow_cache_path()
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(flow_id, encoding="utf-8")
    except OSError:
        logger.warning("Could not cache gallery flow id")
    return flow_id


def add_youtube_gallery_task(
    env_id: str,
    resource_url: str,
    schedule_at: int,
    title: str,
) -> str:
    push_resource_url_to_gallery(env_id, resource_url)
    flow_id = ensure_youtube_gallery_flow_id()
    # Phone is already ON after ADB. Do not idle until the original Excel slot.
    run_at = int(time.time()) + 8
    result = _geelark_api_post(
        "/task/rpa/add",
        {
            "name": f"VF gallery {int(schedule_at)}",
            "scheduleAt": run_at,
            "id": str(env_id),
            "flowId": flow_id,
            "paramMap": {"Title": (title or "Auto publish")[:100]},
        },
    )
    if result.get("code") != 0:
        raise RuntimeError(f"custom RPA add failed: {result.get('msg') or result}")
    task_id = (result.get("data") or {}).get("taskId")
    if not task_id:
        raise RuntimeError("custom RPA add returned no taskId")
    return str(task_id)
