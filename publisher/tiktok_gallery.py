"""TikTok from phone gallery. File is already in Downloads (uploadFile)."""
from __future__ import annotations

from publisher.gallery_rpa import (
    add_gallery_rpa_task,
    ensure_flow_id,
    step_click_text,
    step_close_app,
    step_input_variable,
    step_open_app,
    step_wait,
    step_wait_ele,
    wrap_flow,
)

TT_PKG = "com.zhiliaoapp.musically"
FLOW_TITLE = "VF TikTok gallery"


def build_tiktok_gallery_flow() -> dict:
    contents = [
        step_open_app(TT_PKG),
        step_wait(4000),
        step_click_text("Create"),
        step_wait(2000),
        step_click_text("Upload"),
        step_wait(3000),
        step_wait_ele("Next", search_ms=20000),
        step_click_text("Next", search_ms=20000),
        step_wait(2000),
        step_wait_ele("Next", search_ms=20000),
        step_click_text("Next", search_ms=20000),
        step_wait(2000),
        step_input_variable("Add a description", "Desc"),
        step_wait(1000),
        step_wait_ele("Post", search_ms=30000),
        step_click_text("Post", search_ms=15000),
        step_wait(8000),
        step_close_app(TT_PKG),
    ]
    return wrap_flow(
        contents,
        title=FLOW_TITLE,
        desc="Video Farm: TikTok from gallery, fail if Next/Post missing",
    )


def ensure_tiktok_gallery_flow_id() -> str:
    return ensure_flow_id(
        setting_name="GEELARK_TIKTOK_GALLERY_FLOW_ID",
        cache_setting="GEELARK_TIKTOK_GALLERY_FLOW_CACHE",
        default_cache="/app/data/tiktok_gallery_flow_id.txt",
        build_flow=build_tiktok_gallery_flow,
    )


def add_tiktok_gallery_task(
    env_id: str,
    resource_url: str,
    schedule_at: int,
    description: str = None,
) -> str:
    return add_gallery_rpa_task(
        env_id=env_id,
        resource_url=resource_url,
        schedule_at=schedule_at,
        flow_id=ensure_tiktok_gallery_flow_id(),
        name=f"VF gallery TT {int(schedule_at)}",
        param_map={"Desc": (description or "Auto publish")[:4000]},
    )
