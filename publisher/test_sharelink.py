from unittest.mock import patch

from django.test import SimpleTestCase

from publisher.videofarm_callback import extract_share_link, map_network, notify_videofarm_share_link


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

    def test_maps_excel_network_labels(self):
        self.assertEqual(map_network('ЮТУБ'), 'YOUTUBE')
        self.assertEqual(map_network('тикток'), 'TIKTOK')
        self.assertEqual(map_network('youtube'), 'YOUTUBE')

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
