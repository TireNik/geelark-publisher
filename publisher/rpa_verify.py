"""Classify GeeLark RPA completion. status=3 is not always a real publish.

Stock youtubePubShort (taskType 42) and custom gallery flows can Click-fail
on Next / Upload / Post, then still return status=3.

Working prod (other developer, bak .bak-gallery-20260831-124817): YouTube is
success if after a Next Click-failed the flow still clicks
shorts_post_bottom_button without Click failed. Tasks 2099–2110 landed on
the channel that way. Keep that recovery; also treat No element found on
publish controls as a miss unless the post button succeeded later.
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
    "галерея",
    "загрузить",
    "publish",
    "post",
    "share",
    "далее",
    "опубликовать",
    "shorts_camera_next_button",
    "multi_select_next_button",
    "shorts_post_bottom_button",
)
_POST_BUTTON_MARKERS = (
    "shorts_post_bottom_button",
)


def _has_successful_post_after(lines, failed_index: int) -> bool:
    """True when YouTube still posted via shorts_post_bottom_button (working stock)."""
    for index in range(failed_index + 1, len(lines)):
        line = lines[index]
        lower = line.lower()
        if "click element" not in lower or not any(
            marker in lower for marker in _POST_BUTTON_MARKERS
        ):
            continue
        nearby = "\n".join(lines[index : index + 2])
        if CLICK_FAILED not in nearby and NO_ELEMENT not in nearby:
            return True
    return False


def rpa_is_false_success(logs) -> bool:
    """True when Next / Upload / Post / Share was missing or the click failed.

    GeeLark still returns status=3 / Run successfully in both cases.
    Exception: Next failed but shorts_post_bottom_button click succeeded.
    """
    lines = [str(item) for item in (logs or [])]
    for index, line in enumerate(lines):
        if not any(token in line for token in _STEP_FAILED):
            continue
        window = "\n".join(lines[max(0, index - 6) : index + 1]).lower()
        if any(marker in window for marker in _PUBLISH_MARKERS):
            if _has_successful_post_after(lines, index):
                continue
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
