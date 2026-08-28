"""Classify GeeLark RPA completion. status=3 is not always a real publish.

Stock youtubePubShort (taskType 42) and custom gallery flows can Click-fail
on Next / Upload / Post, then still return status=3.
"""
from __future__ import annotations

# Closest official code: "Preview completed and click Next failed".
FAKE_SUCCESS_FAIL_CODE = 20212

CLICK_FAILED = "Click failed, please check whether the element exists"
NO_ELEMENT = "No element found"
_STEP_FAILED = (CLICK_FAILED, NO_ELEMENT)
_PUBLISH_MARKERS = (
    "upload short",
    "text：next",
    "text:next",
    "create a short",
    "gallery",
    "publish",
    "post",
    "share",
    "далее",
    "опубликовать",
    "shorts_camera_next_button",
    "multi_select_next_button",
)


def rpa_is_false_success(logs) -> bool:
    """True when Next / Upload / Post / Share was missing or the click failed.

    GeeLark still returns status=3 / Run successfully in both cases.
    """
    lines = [str(item) for item in (logs or [])]
    for index, line in enumerate(lines):
        if not any(token in line for token in _STEP_FAILED):
            continue
        window = "\n".join(lines[max(0, index - 6) : index + 1]).lower()
        if any(marker in window for marker in _PUBLISH_MARKERS):
            return True
    return False


def youtube_rpa_is_false_success(logs) -> bool:
    return rpa_is_false_success(logs)


def classify_completed_rpa(social_network: str, logs) -> str:
    """Return 'false_success' or 'success' for a GeeLark status=3 task."""
    if rpa_is_false_success(logs):
        return "false_success"
    return "success"


def false_success_message() -> str:
    return (
        "GeeLark: RPA не нажал Upload / Next / Post, но вернул status=3. "
        f"Ролик скорее всего не выложен (код {FAKE_SUCCESS_FAIL_CODE})."
    )


def resolve_completed_status(social_network: str, logs):
    """Map GeeLark status=3 + logs to our task status fields."""
    if classify_completed_rpa(social_network, logs) == "false_success":
        return "error", FAKE_SUCCESS_FAIL_CODE, false_success_message()
    return "success", None, ""
