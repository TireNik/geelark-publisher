"""JSON ingest from Video Farm — no Excel round-trip."""
from __future__ import annotations

import hmac
import threading
from datetime import datetime

import requests
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from django.conf import settings

from .models import PublicationTask, UploadSession
from .utils import convert_social_networks, session_worker, split_profile_reference, validate_video_url

INGEST_HEADERS = ('X-Geelark-Ingest-Token', 'X-VideoFarm-Token')


def ingest_token() -> str:
    return (
        (getattr(settings, 'VF_INGEST_TOKEN', None) or '').strip()
        or (getattr(settings, 'VF_SHARELINK_TOKEN', None) or '').strip()
    )


def _token_ok(provided: str, expected: str) -> bool:
    left = (provided or '').encode('utf-8')
    right = (expected or '').encode('utf-8')
    if len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


def ingest_auth_error(request):
    """None if the VF ingest token is valid; otherwise a 401/503 Response."""
    expected = ingest_token()
    if not expected:
        return Response(
            {'success': False, 'error': 'ingest disabled: VF_INGEST_TOKEN empty'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    provided = ''
    for header in INGEST_HEADERS:
        value = request.headers.get(header) or ''
        if value:
            provided = value
            break
    if not _token_ok(provided, expected):
        return Response(
            {'success': False, 'error': 'invalid token'},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    return None


def parse_ingest_item(raw: dict, index: int) -> tuple[dict | None, dict | None]:
    if not isinstance(raw, dict):
        return None, {'index': index, 'error': 'item must be an object'}
    profile_raw = str(raw.get('profileId') or raw.get('profile_id') or '').strip()
    network_raw = str(raw.get('socialNetwork') or raw.get('social_network') or '').strip()
    video_url = str(raw.get('videoUrl') or raw.get('video_url') or '').strip()
    title = str(raw.get('title') or '').strip()
    comment = str(raw.get('comment') or '').strip()
    if not profile_raw:
        return None, {'index': index, 'error': 'profileId required'}
    if not network_raw:
        return None, {'index': index, 'error': 'socialNetwork required'}
    network = convert_social_networks(network_raw)
    if not network:
        return None, {'index': index, 'error': f'unsupported socialNetwork: {network_raw}'}
    if not validate_video_url(video_url):
        return None, {'index': index, 'error': 'videoUrl must be HTTP(S) or Yandex Disk'}
    profile_number, profile_id = split_profile_reference(profile_raw)
    if not profile_id:
        return None, {'index': index, 'error': 'profileId has empty GeeLark env id'}
    external_id = str(
        raw.get('externalId') or raw.get('external_id') or raw.get('name') or ''
    ).strip()[:64]
    return {
        'profile_number': profile_number,
        'profile_id': profile_id,
        'social_network': network,
        'video_url': video_url,
        'title': (title or comment)[:255],
        'comment': comment or title,
        'external_id': external_id,
    }, None


def head_video_url(url: str) -> dict:
    try:
        resp = requests.head(url, timeout=15, allow_redirects=True)
        if resp.status_code in (403, 404, 405, 501):
            resp = requests.get(
                url,
                timeout=15,
                stream=True,
                allow_redirects=True,
                headers={'Range': 'bytes=0-0'},
            )
            resp.close()
        ok = 200 <= resp.status_code < 300
        return {
            'videoUrl': url,
            'ok': ok,
            'status': resp.status_code,
            'contentType': resp.headers.get('Content-Type', ''),
            'contentLength': resp.headers.get('Content-Length'),
        }
    except requests.RequestException as exc:
        return {
            'videoUrl': url,
            'ok': False,
            'status': 0,
            'error': str(exc),
        }


class JsonIngestView(APIView):
    parser_classes = (JSONParser,)
    authentication_classes = ()
    permission_classes = ()
    # True on /api/ingest/test/ — never creates a session, even if body says dryRun=false.
    force_dry_run = False

    def post(self, request):
        auth_error = ingest_auth_error(request)
        if auth_error is not None:
            return auth_error

        body = request.data if isinstance(request.data, dict) else {}
        items = body.get('items') or []
        dry_run = self.force_dry_run or bool(body.get('dryRun') or body.get('dry_run'))
        if not isinstance(items, list) or not items:
            return Response(
                {'success': False, 'error': 'items must be a non-empty list'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        parsed = []
        errors = []
        for idx, raw in enumerate(items):
            row, err = parse_ingest_item(raw, idx)
            if err:
                errors.append(err)
            else:
                parsed.append(row)
        if errors:
            return Response(
                {'success': False, 'error': 'invalid items', 'details': errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if dry_run:
            checks = [head_video_url(row['video_url']) for row in parsed]
            all_ok = all(c.get('ok') for c in checks)
            return Response(
                {
                    'success': all_ok,
                    'dryRun': True,
                    'totalTasks': len(parsed),
                    'checks': checks,
                },
                status=status.HTTP_200_OK if all_ok else status.HTTP_400_BAD_REQUEST,
            )

        session = UploadSession.objects.create(
            name=f"Video Farm {datetime.now().strftime('%d.%m.%Y %H:%M')} ({len(parsed)} шт.)",
            status='pending',
        )
        now = datetime.now()
        PublicationTask.objects.bulk_create([
            PublicationTask(
                session=session,
                profile_number=row['profile_number'],
                profile_id=row['profile_id'],
                social_network=row['social_network'],
                video_url=row['video_url'],
                title=row['title'],
                comment=row['comment'],
                publish_time=now,
                external_id=row.get('external_id') or '',
            )
            for row in parsed
        ])
        thread = threading.Thread(target=session_worker, args=(session.id,), daemon=False)
        thread.start()
        return Response(
            {
                'success': True,
                'dryRun': False,
                'sessionId': session.id,
                'session_id': session.id,
                'totalTasks': len(parsed),
                'statusUrl': f'/status/{session.id}/',
                'status_url': f'/status/{session.id}/',
            },
            status=status.HTTP_201_CREATED,
        )


class JsonIngestTestView(JsonIngestView):
    """Token-only dry-run. Not linked from the Excel UI. Never starts phones."""

    force_dry_run = True
