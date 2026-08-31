from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from publisher.models import PublicationTask, UploadSession
from publisher.retry import RetryExternalView, requeue_by_external_ids


class RequeueByExternalIdTests(TestCase):
    def setUp(self):
        self.session = UploadSession.objects.create(name='retry-test')
        self.old_start = timezone.now() - timedelta(hours=1)
        self.task = PublicationTask.objects.create(
            session=self.session,
            profile_id='env-1',
            social_network='YouTube',
            video_url='https://cdn.example/v.mp4',
            comment='c',
            publish_time=self.old_start,
            status='error',
            error_message='timeout',
            geelark_task_id='gid-1',
            geelark_started_at=self.old_start,
            resource_url='https://oss.example/v.mp4',
            external_id='vf-entry-10',
        )

    def test_resets_error_and_started_at(self):
        result = requeue_by_external_ids(['vf-entry-10'])
        self.task.refresh_from_db()
        self.assertEqual(result['retried'][0]['taskId'], self.task.id)
        self.assertEqual(self.task.status, 'prepared')
        self.assertEqual(self.task.geelark_task_id, '')
        self.assertIsNone(self.task.geelark_started_at)
        self.assertEqual(self.task.error_message, '')
        self.assertGreaterEqual(self.task.publish_time, self.old_start)

    def test_skips_success_and_missing(self):
        self.task.status = 'success'
        self.task.save(update_fields=['status'])
        result = requeue_by_external_ids(['vf-entry-10', 'vf-entry-99'])
        self.assertEqual(result['retried'], [])
        self.assertEqual(result['missing'], ['vf-entry-99'])
        self.assertEqual(result['skipped'][0]['reason'], 'not_failed')


class RetryExternalViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = RetryExternalView.as_view()
        self.session = UploadSession.objects.create(name='retry-api')
        PublicationTask.objects.create(
            session=self.session,
            profile_id='env-1',
            social_network='TikTok',
            video_url='https://cdn.example/v.mp4',
            comment='c',
            publish_time=timezone.now(),
            status='error',
            resource_url='https://oss.example/v.mp4',
            external_id='vf-entry-11',
        )

    def test_unauthorized(self):
        with override_settings(VF_INGEST_TOKEN='secret', VF_SHARELINK_TOKEN=''):
            request = self.factory.post(
                '/api/retry/',
                {'externalIds': ['vf-entry-11']},
                format='json',
            )
            response = self.view(request)
        self.assertEqual(response.status_code, 401)

    def test_retries_with_token(self):
        with override_settings(VF_INGEST_TOKEN='secret', VF_SHARELINK_TOKEN=''):
            request = self.factory.post(
                '/api/retry/',
                {'externalIds': ['vf-entry-11']},
                format='json',
                HTTP_X_GEELARK_INGEST_TOKEN='secret',
            )
            response = self.view(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['retried']), 1)
        self.assertEqual(response.data['retried'][0]['externalId'], 'vf-entry-11')
