"""Push GeeLark shareLink back to Video Farm for publication stats."""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

SHARE_LINK_KEYS = (
    'shareLink',
    'share_link',
    'shareUrl',
    'share_url',
    'videoUrl',
    'video_url',
)


def extract_share_link(item) -> str:
    if not isinstance(item, dict):
        return ''
    for key in SHARE_LINK_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.strip().lower().startswith('http'):
            return value.strip()
    nested = item.get('data')
    if isinstance(nested, dict):
        return extract_share_link(nested)
    return ''


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
