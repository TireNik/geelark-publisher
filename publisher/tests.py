from django.test import SimpleTestCase

from publisher.utils import (
    is_direct_http_video_url,
    is_yandex_disk_url,
    validate_video_url,
    validate_yandex_disk_url,
)


class VideoUrlValidationTests(SimpleTestCase):
    def test_yandex_disk_urls(self):
        self.assertTrue(is_yandex_disk_url('https://disk.yandex.ru/i/FGShQav9zoizug'))
        self.assertTrue(is_yandex_disk_url('https://yadi.sk/i/abc'))
        self.assertTrue(validate_yandex_disk_url('https://disk.yandex.ru/d/xxx'))
        self.assertTrue(validate_video_url('https://disk.yandex.ru/i/xxx'))

    def test_direct_http_urls(self):
        vf = (
            'https://vf.example.com/api/public/media/jobs/42/final'
            '?token=eyJhbGciOiJIUzI1NiJ9.abc.def'
        )
        self.assertTrue(is_direct_http_video_url(vf))
        self.assertTrue(validate_video_url(vf))
        self.assertTrue(validate_video_url('http://localhost:8080/api/public/media/jobs/1/final?token=t'))
        long_token = 'a' * 180
        long_vf = (
            'https://ozon-panel.ru/video-farm/api/public/media/jobs/2630/final'
            f'?token={long_token}'
        )
        self.assertTrue(validate_video_url(long_vf))
        self.assertGreater(len(long_vf), 200)
        self.assertFalse(is_yandex_disk_url(vf))

    def test_rejects_invalid(self):
        self.assertFalse(validate_video_url(''))
        self.assertFalse(validate_video_url(None))
        self.assertFalse(validate_video_url('ftp://files.example.com/a.mp4'))
        self.assertFalse(validate_video_url('not-a-url'))
        self.assertFalse(is_direct_http_video_url('https://disk.yandex.ru/i/xxx'))
