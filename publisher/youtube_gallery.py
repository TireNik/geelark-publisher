"""YouTube Shorts from phone gallery. File is already in Downloads (uploadFile)."""
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

YT_PKG = "com.google.android.youtube"
FLOW_TITLE = "VF YouTube gallery Short"


def build_youtube_gallery_flow() -> dict:
    contents = [
        step_open_app(YT_PKG),
        step_wait(4000),
        step_click_text("Create"),
        step_wait(2000),
        step_click_text("Create a short"),
        step_wait(3000),
        step_click_text("Gallery"),
        step_wait(2500),
        step_wait_ele("Next", search_ms=20000),
        step_click_text("Next", search_ms=20000),
        step_wait(2000),
        step_wait_ele("Next", search_ms=20000),
        step_click_text("Next", search_ms=20000),
        step_wait(2000),
        step_input_variable("Add a title that's more than 4 characters", "Title"),
        step_wait(1000),
        step_wait_ele("Upload Short", search_ms=30000),
        step_click_text("Upload Short", search_ms=15000),
        step_wait_ele("Uploaded to Your Videos", search_ms=60000),
        step_close_app(YT_PKG),
    ]
    return wrap_flow(
        contents,
        title=FLOW_TITLE,
        desc="Video Farm: YouTube Short from gallery, fail if Next/Upload Short missing",
    )


def ensure_youtube_gallery_flow_id() -> str:
    return ensure_flow_id(
        setting_name="GEELARK_YOUTUBE_GALLERY_FLOW_ID",
        cache_setting="GEELARK_YOUTUBE_GALLERY_FLOW_CACHE",
        default_cache="/app/data/youtube_gallery_flow_id.txt",
        build_flow=build_youtube_gallery_flow,
    )


def add_youtube_gallery_task(
    env_id: str,
    resource_url: str,
    schedule_at: int,
    title: str,
) -> str:
    return add_gallery_rpa_task(
        env_id=env_id,
        resource_url=resource_url,
        schedule_at=schedule_at,
        flow_id=ensure_youtube_gallery_flow_id(),
        name=f"VF gallery YT {int(schedule_at)}",
        param_map={"Title": (title or "Auto publish")[:100]},
    )
