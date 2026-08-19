from unittest.mock import patch

from django.test import SimpleTestCase

from publisher.videofarm_callback import (
    extract_share_link,
    map_network,
    notify_videofarm_share_link,
    resolve_published_share_link,
)


class ShareLinkCallbackTests(SimpleTestCase):
    def test_extracts_share_link_from_geelark_item(self):
        item = {
            'id': 't1',
            'status': 3,
            'shareLink': 'https://www.youtube.com/shorts/abcdefghijk',
        }
        self.assertEqual(
            extract_share_link(item),
            'https://www.youtube.com/shorts/abcdefghijk',
        )

    def test_extracts_nested_share_url(self):
        item = {'data': {'shareUrl': 'https://www.tiktok.com/@x/video/12345678901'}}
        self.assertEqual(
            extract_share_link(item),
            'https://www.tiktok.com/@x/video/12345678901',
        )

    def test_ignores_pipeline_video_url(self):
        item = {
            'status': 3,
            'shareLink': '',
            'videoUrl': 'https://vf.example/api/public/media/jobs/4109/final?token=abc',
        }
        self.assertEqual(extract_share_link(item), '')

    def test_extracts_youtube_url_from_task_detail_logs(self):
        item = {
            'status': 3,
            'shareLink': '',
            'logs': [
                '[2026-08-19 08:00:00] Waiting for execution',
                'Published https://www.youtube.com/shorts/abcdefghijk successfully',
            ],
        }
        self.assertEqual(
            extract_share_link(item),
            'https://www.youtube.com/shorts/abcdefghijk',
        )

    def test_maps_excel_network_labels(self):
        self.assertEqual(map_network('ЮТУБ'), 'YOUTUBE')
        self.assertEqual(map_network('тикток'), 'TIKTOK')
        self.assertEqual(map_network('youtube'), 'YOUTUBE')

    def test_resolve_uses_query_share_link_without_detail(self):
        called = {'n': 0}

        def loader():
            called['n'] += 1
            return {}

        found = resolve_published_share_link(
            {'status': 3, 'shareLink': 'https://youtu.be/abcdefghijk'},
            detail_loader=loader,
        )
        self.assertEqual(found, 'https://youtu.be/abcdefghijk')
        self.assertEqual(called['n'], 0)

    def test_resolve_loads_detail_when_query_share_link_empty(self):
        found = resolve_published_share_link(
            {'status': 3, 'shareLink': ''},
            detail_loader=lambda: {
                'logs': ['done https://www.tiktok.com/@x/video/12345678901'],
            },
        )
        self.assertEqual(found, 'https://www.tiktok.com/@x/video/12345678901')

    def test_resolve_skips_detail_while_task_running(self):
        called = {'n': 0}

        def loader():
            called['n'] += 1
            return {'logs': ['https://www.youtube.com/shorts/abcdefghijk']}

        found = resolve_published_share_link(
            {'status': 2, 'shareLink': ''},
            detail_loader=loader,
        )
        self.assertEqual(found, '')
        self.assertEqual(called['n'], 0)

    @patch('publisher.videofarm_callback.requests.post')
    def test_skips_notify_without_endpoint(self, post):
        with self.settings(VF_SHARELINK_URL='', VF_SHARELINK_TOKEN='secret'):
            self.assertFalse(notify_videofarm_share_link(
                'https://vf.example/api/public/media/jobs/1/final?token=a',
                'https://www.youtube.com/shorts/abcdefghijk',
                'ЮТУБ',
            ))
        post.assert_not_called()

    @patch('publisher.videofarm_callback.requests.post')
    def test_posts_share_link_to_video_farm(self, post):
        post.return_value.status_code = 200
        post.return_value.text = '{}'
        with self.settings(
            VF_SHARELINK_URL='https://vf.example/api/public/publish/share-link',
            VF_SHARELINK_TOKEN='secret',
        ):
            self.assertTrue(notify_videofarm_share_link(
                'https://vf.example/api/public/media/jobs/42/final?token=tok',
                'https://www.youtube.com/shorts/abcdefghijk',
                'ЮТУБ',
            ))
        post.assert_called_once()
        args, kwargs = post.call_args
        self.assertEqual(args[0], 'https://vf.example/api/public/publish/share-link')
        self.assertEqual(kwargs['json']['network'], 'YOUTUBE')
        self.assertEqual(kwargs['headers']['X-Geelark-Ingest-Token'], 'secret')
