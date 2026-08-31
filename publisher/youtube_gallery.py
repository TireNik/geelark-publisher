"""YouTube Shorts from phone gallery. File is already in Downloads (uploadFile)."""
from __future__ import annotations

from publisher.gallery_rpa import (
    add_gallery_rpa_task,
    ensure_flow_id,
    step_close_app,
    step_open_app,
    step_wait,
    steps_click_any,
    steps_input_any,
    steps_wait_any,
    wrap_flow,
)

YT_PKG = "com.google.android.youtube"
FLOW_TITLE = "VF YouTube gallery Short v4"
NEXT_IDS = (
    "shorts_camera_next_button",
    "com.google.android.youtube:id/shorts_camera_next_button",
    "multi_select_next_button",
)
# Working stock youtubePubShort (tasks 2099–2110): this is the real Post.
POST_IDS = (
    "shorts_post_bottom_button",
    "com.google.android.youtube:id/shorts_post_bottom_button",
)


def build_youtube_gallery_flow() -> dict:
    contents = [
        step_open_app(YT_PKG),
        step_wait(8000),
        *steps_click_any(
            ids=("com.google.android.youtube:id/reel_camera_button",),
            descs=("Create a video or post", "Create"),
            texts=("Create", "Создать"),
            prefix="yt_create",
            search_ms=10000,
        ),
        step_wait(2000),
        *steps_click_any(
            texts=("Create a short", "Создать Short", "Short"),
            prefix="yt_short",
            search_ms=8000,
        ),
        step_wait(2500),
        *steps_click_any(
            descs=("Gallery",),
            texts=("Gallery", "Галерея"),
            prefix="yt_gal",
            search_ms=10000,
        ),
        step_wait(2500),
        *steps_click_any(
            ids=NEXT_IDS,
            texts=("Next", "Далее"),
            prefix="yt_next1",
            search_ms=20000,
        ),
        step_wait(2000),
        *steps_click_any(
            ids=NEXT_IDS,
            texts=("Next", "Далее"),
            prefix="yt_next2",
            search_ms=20000,
        ),
        step_wait(2000),
        *steps_input_any(
            (
                "Add a title that's more than 4 characters",
                "Добавьте название длиннее 4 символов",
                "Название",
            ),
            "Title",
        ),
        step_wait(1000),
        *steps_click_any(
            ids=POST_IDS,
            texts=("Upload Short", "Загрузить Short", "Опубликовать", "Upload"),
            prefix="yt_upload",
            search_ms=15000,
        ),
        *steps_wait_any(
            texts=(
                "Uploaded to Your Videos",
                "Загружено в ваши видео",
                "Видео загружено",
            ),
            search_ms=60000,
            prefix="yt_done",
        ),
        step_close_app(YT_PKG),
    ]
    return wrap_flow(
        contents,
        title=FLOW_TITLE,
        desc="Video Farm: YouTube Short from gallery; Post via shorts_post_bottom_button",
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
