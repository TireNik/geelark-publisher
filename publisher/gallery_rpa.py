"""Shared custom RPA helpers: English UI, errorType=stop, flow import + rpa/add."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from django.conf import settings

from publisher.gallery_phone import ensure_resource_on_gallery
from publisher.utils import _geelark_api_post

logger = logging.getLogger(__name__)


def step_wait(ms: int) -> dict:
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


def step_click_text(text: str, search_ms: int = 8000) -> dict:
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


def step_wait_ele(text: str, search_ms: int = 15000, variable: str = "") -> dict:
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


def step_input_variable(placeholder: str, variable: str, search_ms: int = 8000) -> dict:
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


def step_open_app(package: str, timeout: int = 30000) -> dict:
    return {
        "type": "openApp",
        "config": {"packgename": package, "remark": "", "timeout": timeout},
    }


def step_close_app(package: str, timeout: int = 15000) -> dict:
    return {
        "type": "closeApp",
        "config": {"packgename": package, "remark": "", "timeout": timeout},
    }


def wrap_flow(contents: list, *, title: str, desc: str) -> dict:
    return {
        "content": {
            "contents": contents,
            "errorType": "stop",
            "isDebug": False,
            "timeOut": "8",
            "contentType": "phone",
        },
        "desc": desc,
        "title": title,
    }


def ensure_flow_id(
    *,
    setting_name: str,
    cache_setting: str,
    default_cache: str,
    build_flow,
) -> str:
    configured = str(getattr(settings, setting_name, "") or "").strip()
    if configured:
        return configured
    cache_raw = str(getattr(settings, cache_setting, "") or "").strip()
    cache = Path(cache_raw) if cache_raw else Path(default_cache)
    existing = ""
    try:
        if cache.is_file():
            existing = cache.read_text(encoding="utf-8").strip()
    except OSError:
        existing = ""
    payload = {"gal": json.dumps(build_flow(), ensure_ascii=False)}
    if existing:
        payload["id"] = existing
    result = _geelark_api_post("/task/flow/import", payload)
    if result.get("code") != 0:
        raise RuntimeError(f"flow import failed: {result.get('msg') or result}")
    flow_id = str((result.get("data") or {}).get("id") or existing)
    if not flow_id:
        raise RuntimeError("flow import returned no id")
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(flow_id, encoding="utf-8")
    except OSError:
        logger.warning("Could not cache gallery flow id at %s", cache)
    return flow_id


def add_gallery_rpa_task(
    *,
    env_id: str,
    resource_url: str,
    schedule_at: int,
    flow_id: str,
    name: str,
    param_map: dict,
) -> str:
    ensure_resource_on_gallery(env_id, resource_url)
    run_at = int(time.time()) + 8
    result = _geelark_api_post(
        "/task/rpa/add",
        {
            "name": name,
            "scheduleAt": run_at,
            "id": str(env_id),
            "flowId": flow_id,
            "paramMap": param_map,
        },
    )
    if result.get("code") != 0:
        raise RuntimeError(f"custom RPA add failed: {result.get('msg') or result}")
    task_id = (result.get("data") or {}).get("taskId")
    if not task_id:
        raise RuntimeError("custom RPA add returned no taskId")
    return str(task_id)
