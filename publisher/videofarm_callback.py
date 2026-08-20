"""Legacy GeeLark shareLink → VF callback.

Not used by sync_geelark_statuses: publication stats come from ig-stats /
hashtag harvest, not GeeLark shareLink (usually empty on youtubePubShort).
Kept for tests and a possible one-off backfill.
"""
import logging
import re

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Named fields from GeeLark task/query (shareLink) and occasional aliases.
# Do not treat videoUrl as the publication URL: that is the VF/GeeLark file.
SHARE_LINK_KEYS = (
    'shareLink',
    'share_link',
    'shareUrl',
    'share_url',
)

_YOUTUBE_URL = re.compile(
    r'https?://(?:www\.)?(?:youtube\.com/(?:shorts/|watch\?[^ \s\"\'<>]*v=|embed/)|youtu\.be/)'
    r'[A-Za-z0-9_-]{11}[^\s\"\'<>]*',
    re.IGNORECASE,
)
_TIKTOK_URL = re.compile(
    r'https?://(?:www\.|m\.)?tiktok\.com/[^\s\"\'<>]*?/video/\d{5,}[^\s\"\'<>]*',
    re.IGNORECASE,
)
_TIKTOK_MOBILE = re.compile(
    r'https?://m\.tiktok\.com/v/\d{5,}[^\s\"\'<>]*',
    re.IGNORECASE,
)
_TRAILING_PUNCT = re.compile(r'[),.;]+$')


def is_social_share_url(value: str) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text.lower().startswith('http'):
        return False
    lower = text.lower()
    if any(marker in lower for marker in (
        'geelark.com',
        'geelark.cn',
        '/jobs/',
        '/final',
        'material.geelark',
    )):
        return False
    if _YOUTUBE_URL.search(text) or _TIKTOK_URL.search(text) or _TIKTOK_MOBILE.search(text):
        return True
    return False


def _clean_url(value: str) -> str:
    return _TRAILING_PUNCT.sub('', (value or '').strip())


def _urls_in_text(text: str):
    if not isinstance(text, str):
        return
    for pattern in (_YOUTUBE_URL, _TIKTOK_URL, _TIKTOK_MOBILE):
        for match in pattern.findall(text):
            cleaned = _clean_url(match)
            if is_social_share_url(cleaned):
                yield cleaned


def extract_share_link(item) -> str:
    """Pick a YouTube/TikTok publication URL from a GeeLark task payload.

    GeeLark documents shareLink on POST /open/v1/task/query. When that field
    is empty, Task Detail logs (POST /open/v1/task/detail) may still contain
    the published URL.
    """
    found = []

    def walk(node, from_key=None):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in SHARE_LINK_KEYS and isinstance(value, str):
                    cleaned = _clean_url(value)
                    if is_social_share_url(cleaned):
                        found.append(cleaned)
                walk(value, key)
            return
        if isinstance(node, list):
            for child in node:
                walk(child, from_key)
            return
        if isinstance(node, str):
            if from_key in SHARE_LINK_KEYS:
                cleaned = _clean_url(node)
                if is_social_share_url(cleaned):
                    found.append(cleaned)
                    return
            found.extend(_urls_in_text(node))

    walk(item)
    return found[0] if found else ''


def resolve_published_share_link(query_item, detail_loader=None) -> str:
    """Use task/query shareLink; on success with empty field load task/detail."""
    found = extract_share_link(query_item)
    if found:
        return found
    try:
        status = int((query_item or {}).get('status'))
    except (TypeError, ValueError):
        return ''
    if status != 3 or detail_loader is None:
        return ''
    try:
        detail = detail_loader()
    except Exception as exc:
        logger.warning('GeeLark task/detail failed while looking for shareLink: %s', exc)
        return ''
    return extract_share_link(detail)


def map_network(social_network: str) -> str:
    text = (social_network or '').strip().lower()
    if text in {'youtube', 'ютуб', 'yt'}:
        return 'YOUTUBE'
    if text in {'tiktok', 'тикток', 'tt'}:
        return 'TIKTOK'
    return (social_network or '').strip().upper()


def notify_videofarm_share_link(video_url, share_url, social_network) -> bool:
    endpoint = (getattr(settings, 'VF_SHARELINK_URL', None) or '').strip()
    token = (getattr(settings, 'VF_SHARELINK_TOKEN', None) or '').strip()
    if not endpoint or not share_url:
        return False
    try:
        response = requests.post(
            endpoint,
            json={
                'videoUrl': str(video_url or ''),
                'shareUrl': str(share_url),
                'network': map_network(social_network),
            },
            headers={
                'Content-Type': 'application/json',
                'X-Geelark-Ingest-Token': token,
            },
            timeout=15,
        )
        if response.status_code >= 400:
            logger.warning(
                'Video Farm shareLink ingest failed: %s %s',
                response.status_code,
                (response.text or '')[:200],
            )
            return False
        return True
    except requests.RequestException as exc:
        logger.warning('Video Farm shareLink ingest error: %s', exc)
        return False
