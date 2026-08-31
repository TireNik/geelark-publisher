"""Requeue failed VF publications by external_id (vf-entry-{id})."""
from __future__ import annotations

from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from publisher.models import PublicationTask, refresh_session_status

RETRYABLE = frozenset({'error', 'stopping'})


def requeue_by_external_ids(external_ids):
    """Reset the latest matching task for each id to prepared.

    Clears GeeLark ids, fail code, and geelark_started_at so the 8-minute
    watchdog does not cancel the retry using the previous attempt's clock.
    """
    requested = []
    seen = set()
    for raw in external_ids or []:
        value = str(raw or '').strip()
        if not value or value in seen:
            continue
        seen.add(value)
        requested.append(value)

    retried = []
    missing = []
    skipped = []
    now = timezone.now()

    for external_id in requested:
        task = (
            PublicationTask.objects.filter(external_id=external_id)
            .order_by('-id')
            .first()
        )
        if task is None:
            missing.append(external_id)
            continue
        if task.status not in RETRYABLE:
            skipped.append(
                {
                    'externalId': external_id,
                    'taskId': task.id,
                    'status': task.status,
                    'reason': 'not_failed',
                }
            )
            continue
        if not task.resource_url:
            skipped.append(
                {
                    'externalId': external_id,
                    'taskId': task.id,
                    'status': task.status,
                    'reason': 'no_resource_url',
                }
            )
            continue

        task.status = 'prepared'
        task.error_message = ''
        task.geelark_task_id = ''
        task.geelark_status = None
        task.geelark_fail_code = None
        task.geelark_rpa_cost_sec = None
        task.geelark_started_at = None
        task.geelark_cancel_requested_at = None
        task.processed_at = None
        task.share_link = ''
        task.publish_time = now
        task.save(
            update_fields=[
                'status',
                'error_message',
                'geelark_task_id',
                'geelark_status',
                'geelark_fail_code',
                'geelark_rpa_cost_sec',
                'geelark_started_at',
                'geelark_cancel_requested_at',
                'processed_at',
                'share_link',
                'publish_time',
            ]
        )
        refresh_session_status(task.session)
        retried.append(
            {
                'externalId': external_id,
                'taskId': task.id,
                'status': task.status,
            }
        )

    return {
        'success': True,
        'retried': retried,
        'missing': missing,
        'skipped': skipped,
    }


class RetryExternalView(APIView):
    parser_classes = (JSONParser,)
    authentication_classes = ()
    permission_classes = ()

    def post(self, request):
        from publisher.json_ingest import ingest_auth_error

        auth_error = ingest_auth_error(request)
        if auth_error is not None:
            return auth_error

        body = request.data if isinstance(request.data, dict) else {}
        raw_ids = body.get('externalIds') or body.get('external_ids') or []
        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {'success': False, 'error': 'externalIds must be a non-empty list'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        result = requeue_by_external_ids(raw_ids)
        return Response(result, status=status.HTTP_200_OK)
