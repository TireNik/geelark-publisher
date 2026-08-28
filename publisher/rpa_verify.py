"""Classify GeeLark RPA completion. status=3 is not always a real publish.

Stock youtubePubShort (taskType 42) often Click-fails on «Upload Short» / Next,
OCR-taps coordinates, waits ~2 min, closes YouTube, and still returns status=3.
"""
from __future__ import annotations

# Closest official code: "Preview completed and click Next failed".
FAKE_SUCCESS_FAIL_CODE = 20212

CLICK_FAILED = "Click failed, please check whether the element exists"
# Text labels plus YouTube resource-ids from prod task/detail (2026-08-26+).
_PUBLISH_MARKERS = (
    "upload short",
    "text：next",
    "text:next",
    "publish",
    "далее",
    "shorts_camera_next_button",
    "multi_select_next_button",
)


def youtube_rpa_is_false_success(logs) -> bool:
    """True when the hidden YouTube Shorts flow failed to press Next / Upload."""
    lines = [str(item) for item in (logs or [])]
    for index, line in enumerate(lines):
        if CLICK_FAILED not in line:
            continue
        window = "\n".join(lines[max(0, index - 6) : index + 1]).lower()
        if any(marker in window for marker in _PUBLISH_MARKERS):
            return True
    return False


def classify_completed_rpa(social_network: str, logs) -> str:
    """Return 'false_success' or 'success' for a GeeLark status=3 task."""
    network = (social_network or "").strip().lower()
    if network == "youtube" and youtube_rpa_is_false_success(logs):
        return "false_success"
    return "success"


def false_success_message() -> str:
    return (
        "GeeLark: RPA не нажал Upload Short / Next, но вернул status=3. "
        f"Ролик скорее всего не выложен (код {FAKE_SUCCESS_FAIL_CODE})."
    )


def resolve_completed_status(social_network: str, logs):
    """Map GeeLark status=3 + logs to our task status fields."""
    if classify_completed_rpa(social_network, logs) == "false_success":
        return "error", FAKE_SUCCESS_FAIL_CODE, false_success_message()
    return "success", None, ""
