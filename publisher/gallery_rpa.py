"""Shared custom RPA helpers: RU/EN UI, errorType=stop, flow import + rpa/add."""
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


def _click_filters(filters: list, search_ms: int = 8000, variable: str = "") -> dict:
    return {
        "type": "click",
        "config": {
            "filters": filters,
            "remark": "",
            "searchTime": search_ms,
            "serial": 1,
            "serialMax": 50,
            "serialMin": 1,
            "serialType": "fixedValue",
            "variable": variable,
        },
    }


def _wait_filters(
    filters: list,
    search_ms: int = 15000,
    variable: str = "",
    *,
    optional: bool = False,
) -> dict:
    config = {
        "filters": filters,
        "remark": "",
        "searchTime": search_ms,
        "serial": 1,
        "serialMax": 50,
        "serialMin": 1,
        "serialType": "fixedValue",
        "variable": variable,
    }
    if optional:
        # Probe: missing EN/RU label must not kill the flow (session 294).
        config["errorType"] = "skip"
    return {"type": "waitEle", "config": config}


def step_click_text(text: str, search_ms: int = 8000) -> dict:
    return _click_filters([{"content": text, "type": "text"}], search_ms)


def step_click_id(element_id: str, search_ms: int = 8000) -> dict:
    return _click_filters([{"content": element_id, "type": "id"}], search_ms)


def step_click_desc(desc: str, search_ms: int = 8000) -> dict:
    return _click_filters([{"content": desc, "type": "desc"}], search_ms)


def step_wait_ele(
    text: str,
    search_ms: int = 15000,
    variable: str = "",
    *,
    optional: bool = False,
) -> dict:
    return _wait_filters(
        [{"content": text, "type": "text"}],
        search_ms,
        variable,
        optional=optional,
    )


def step_if_exist(variable: str, then_steps: list, else_steps: list | None = None) -> dict:
    return {
        "type": "ifElse",
        "config": {
            "children": then_steps,
            "condition": [variable],
            "hiddenChildren": False,
            "other": else_steps or [],
            "relation": "exist",
            "remark": "",
        },
    }


def _or_filters(
    *,
    ids: tuple[str, ...] = (),
    texts: tuple[str, ...] = (),
    descs: tuple[str, ...] = (),
) -> list:
    """GeeLark treats several filters on one click/wait as OR (official import sample)."""
    return (
        [{"content": item, "type": "id"} for item in ids]
        + [{"content": item, "type": "desc"} for item in descs]
        + [{"content": item, "type": "text"} for item in texts]
    )


def steps_click_any(
    *,
    ids: tuple[str, ...] = (),
    texts: tuple[str, ...] = (),
    descs: tuple[str, ...] = (),
    search_ms: int = 12000,
    prefix: str = "el",
) -> list:
    """One click with RU/EN/id filters. Nested ifElse is Invalid taskStep (session 304)."""
    del prefix
    filters = _or_filters(ids=ids, texts=texts, descs=descs)
    if not filters:
        return []
    return [_click_filters(filters, search_ms)]


def steps_wait_any(
    *,
    texts: tuple[str, ...] = (),
    ids: tuple[str, ...] = (),
    search_ms: int = 20000,
    prefix: str = "wait",
) -> list:
    del prefix
    filters = _or_filters(ids=ids, texts=texts)
    if not filters:
        return []
    return [_wait_filters(filters, search_ms, "")]


def steps_input_any(placeholders: tuple[str, ...], variable: str, search_ms: int = 8000) -> list:
    if not placeholders:
        return []
    return [
        {
            "type": "input",
            "config": {
                "filters": [{"content": item, "type": "text"} for item in placeholders],
                "remark": "",
                "searchTime": search_ms,
                "serial": 1,
                "serialMax": 50,
                "serialMin": 1,
                "serialType": "fixedValue",
                "variable": variable,
            },
        }
    ]


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
