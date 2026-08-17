from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory

from publisher.json_ingest import JsonIngestView, parse_ingest_item
from publisher.utils import add_youtube_task


class ParseIngestItemTests(SimpleTestCase):
    def test_accepts_videofarm_http_and_excel_network(self):
        row, err = parse_ingest_item(
            {
                'profileId': '16/605043047633256588',
                'socialNetwork': 'ЮТУБ',
                'videoUrl': 'https://ozon-panel.ru/video-farm/api/public/media/jobs/1/final?token=abc',
                'title': 'Shorts title',
                'comment': 'Description text',
            },
            0,
        )
        self.assertIsNone(err)
        self.assertEqual(row['profile_number'], '16')
        self.assertEqual(row['profile_id'], '605043047633256588')
        self.assertEqual(row['social_network'], 'YouTube')
        self.assertEqual(row['title'], 'Shorts title')
        self.assertEqual(row['comment'], 'Description text')

    def test_rejects_empty_profile(self):
        row, err = parse_ingest_item(
            {
                'socialNetwork': 'ТИКТОК',
                'videoUrl': 'https://example.com/v.mp4',
            },
            1,
        )
        self.assertIsNone(row)
        self.assertEqual(err['index'], 1)


class JsonIngestViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = JsonIngestView.as_view()
        self.payload = {
            'dryRun': True,
            'items': [
                {
                    'profileId': '1/env1',
                    'socialNetwork': 'ТИКТОК',
                    'videoUrl': 'https://ozon-panel.ru/video-farm/p/abcdefgh',
                    'comment': 'caption',
                }
            ],
        }

    def test_disabled_without_token(self):
        with override_settings(VF_INGEST_TOKEN='', VF_SHARELINK_TOKEN=''):
            request = self.factory.post('/api/ingest/', self.payload, format='json')
            response = self.view(request)
        self.assertEqual(response.status_code, 503)

    def test_unauthorized_wrong_token(self):
        with override_settings(VF_INGEST_TOKEN='secret', VF_SHARELINK_TOKEN=''):
            request = self.factory.post(
                '/api/ingest/',
                self.payload,
                format='json',
                HTTP_X_GEELARK_INGEST_TOKEN='nope',
            )
            response = self.view(request)
        self.assertEqual(response.status_code, 401)

    @patch('publisher.json_ingest.head_video_url')
    def test_dry_run_heads_video_without_session(self, head):
        head.return_value = {
            'videoUrl': 'https://ozon-panel.ru/video-farm/p/abcdefgh',
            'ok': True,
            'status': 200,
            'contentType': 'video/mp4',
            'contentLength': '12',
        }
        with override_settings(VF_INGEST_TOKEN='secret', VF_SHARELINK_TOKEN=''):
            request = self.factory.post(
                '/api/ingest/',
                self.payload,
                format='json',
                HTTP_X_GEELARK_INGEST_TOKEN='secret',
            )
            response = self.view(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['dryRun'])
        self.assertEqual(response.data['totalTasks'], 1)
        head.assert_called_once()


class YoutubeDescriptionTests(SimpleTestCase):
    @patch('publisher.utils.requests.post')
    def test_add_youtube_task_sends_description(self, post):
        post.return_value.status_code = 200
        post.return_value.raise_for_status = lambda: None
        post.return_value.json.return_value = {'code': 0, 'data': {'taskId': 't1'}}
        with override_settings(GEELARK_TOKEN='tok'):
            task_id = add_youtube_task(
                env_id='env',
                resource_url='https://storage.example/v.mp4',
                schedule_at=1,
                title='My title',
                description='Full description',
            )
        self.assertEqual(task_id, 't1')
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['title'], 'My title')
        self.assertEqual(payload['description'], 'Full description')
