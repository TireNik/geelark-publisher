from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from publisher.gallery_phone import (
    GALLERY_REMOTE_PATH,
    ensure_phone_running,
    ensure_resource_on_gallery,
    gallery_publish_mode_enabled,
    reset_gallery_push_cache,
    upload_resource_url_to_phone,
    youtube_gallery_mode_enabled,
)
from publisher.instagram_gallery import add_instagram_gallery_task, build_instagram_gallery_flow
from publisher.rpa_verify import FAKE_SUCCESS_FAIL_CODE, resolve_completed_status
from publisher.test_rpa_verify import PROD_FALSE_SUCCESS
from publisher.tiktok_gallery import add_tiktok_gallery_task, build_tiktok_gallery_flow
from publisher.youtube_gallery import (
    add_youtube_gallery_task,
    build_youtube_gallery_flow,
    ensure_youtube_gallery_flow_id,
)
from publisher.models import PublicationTask, UploadSession
from publisher.views import sync_geelark_statuses
from publisher.utils import add_instagram_task, add_tiktok_task, add_youtube_task


class GalleryModeTests(SimpleTestCase):
    def setUp(self):
        reset_gallery_push_cache()

    @override_settings(GEELARK_PUBLISH_MODE="stock", GEELARK_YOUTUBE_PUBLISH_MODE="stock")
    def test_stock_flag_disables_gallery(self):
        self.assertFalse(gallery_publish_mode_enabled())
        self.assertFalse(youtube_gallery_mode_enabled())

    @override_settings(GEELARK_PUBLISH_MODE="", GEELARK_YOUTUBE_PUBLISH_MODE="")
    def test_unset_mode_defaults_to_gallery(self):
        self.assertTrue(gallery_publish_mode_enabled())
        self.assertTrue(youtube_gallery_mode_enabled())

    @override_settings(GEELARK_PUBLISH_MODE="gallery")
    def test_gallery_opt_in(self):
        self.assertTrue(gallery_publish_mode_enabled())


class YoutubeGalleryFlowTests(SimpleTestCase):
    def test_flow_stops_on_error_and_waits_for_upload(self):
        flow = build_youtube_gallery_flow()
        content = flow["content"]
        self.assertEqual(content["errorType"], "stop")
        dumped = str(content)
        self.assertIn("Upload Short", dumped)
        self.assertIn("Next", dumped)
        self.assertIn("Далее", dumped)
        self.assertIn("Создать", dumped)
        self.assertIn("Галерея", dumped)
        self.assertIn("shorts_camera_next_button", dumped)
        self.assertIn("Uploaded to Your Videos", dumped)
        self.assertNotIn("120000", dumped)

    @override_settings(GEELARK_YOUTUBE_GALLERY_FLOW_ID="flow-fixed")
    def test_configured_flow_id_skips_import(self):
        self.assertEqual(ensure_youtube_gallery_flow_id(), "flow-fixed")

    @patch("publisher.gallery_rpa.ensure_resource_on_gallery")
    @patch("publisher.youtube_gallery.ensure_youtube_gallery_flow_id", return_value="flow-1")
    @patch("publisher.gallery_rpa._geelark_api_post")
    def test_rpa_add_uses_flow_and_title(self, api_post, _flow, push):
        api_post.return_value = {"code": 0, "data": {"taskId": "rpa-9"}}
        task_id = add_youtube_gallery_task(
            env_id="env-1",
            resource_url="https://cdn.example/v.mp4",
            schedule_at=1_700_000_000,
            title="Short #vf_1",
        )
        self.assertEqual(task_id, "rpa-9")
        push.assert_called_once_with("env-1", "https://cdn.example/v.mp4")
        payload = api_post.call_args.args[1]
        self.assertEqual(api_post.call_args.args[0], "/task/rpa/add")
        self.assertEqual(payload["flowId"], "flow-1")
        self.assertEqual(payload["id"], "env-1")
        self.assertEqual(payload["paramMap"]["Title"], "Short #vf_1")
        self.assertGreaterEqual(payload["scheduleAt"], int(timezone.now().timestamp()))


class TikTokInstagramFlowTests(SimpleTestCase):
    def test_tiktok_flow_stops_on_post(self):
        flow = build_tiktok_gallery_flow()
        self.assertEqual(flow["content"]["errorType"], "stop")
        dumped = str(flow)
        self.assertIn("Upload", dumped)
        self.assertIn("Post", dumped)
        self.assertIn("Опубликовать", dumped)
        self.assertIn("Далее", dumped)
        self.assertIn("com.zhiliaoapp.musically", dumped)

    def test_instagram_flow_stops_on_share(self):
        flow = build_instagram_gallery_flow()
        self.assertEqual(flow["content"]["errorType"], "stop")
        dumped = str(flow)
        self.assertIn("Share", dumped)
        self.assertIn("Поделиться", dumped)
        self.assertIn("com.instagram.android", dumped)

    @patch("publisher.gallery_rpa.ensure_resource_on_gallery")
    @patch("publisher.tiktok_gallery.ensure_tiktok_gallery_flow_id", return_value="tt-flow")
    @patch("publisher.gallery_rpa._geelark_api_post")
    def test_tiktok_rpa_param_desc(self, api_post, _flow, push):
        api_post.return_value = {"code": 0, "data": {"taskId": "tt-1"}}
        task_id = add_tiktok_gallery_task("env-1", "https://cdn.example/v.mp4", 1, "cap")
        self.assertEqual(task_id, "tt-1")
        self.assertEqual(api_post.call_args.args[1]["paramMap"]["Desc"], "cap")

    @patch("publisher.gallery_rpa.ensure_resource_on_gallery")
    @patch("publisher.instagram_gallery.ensure_instagram_gallery_flow_id", return_value="ig-flow")
    @patch("publisher.gallery_rpa._geelark_api_post")
    def test_instagram_rpa_param_desc(self, api_post, _flow, push):
        api_post.return_value = {"code": 0, "data": {"taskId": "ig-1"}}
        task_id = add_instagram_gallery_task("env-1", "https://cdn.example/v.mp4", 1, "reel")
        self.assertEqual(task_id, "ig-1")
        self.assertEqual(api_post.call_args.args[1]["paramMap"]["Desc"], "reel")


class PhoneUploadTests(SimpleTestCase):
    def setUp(self):
        reset_gallery_push_cache()

    @patch("publisher.gallery_phone.ensure_phone_running")
    @patch("publisher.gallery_phone._geelark_api_post")
    def test_upload_file_polls_until_done(self, api_post, _boot):
        api_post.side_effect = [
            {"code": 0, "data": {"taskId": "up-1"}},
            {"code": 0, "data": {"status": 2}},
            {"code": 0, "data": {"status": 3}},
            {"code": 0, "data": {"status": True, "output": "ok"}},
        ]
        with patch("publisher.gallery_phone.time.sleep"):
            remote = upload_resource_url_to_phone("env-1", "https://cdn.example/v.mp4")
        self.assertEqual(remote, GALLERY_REMOTE_PATH)
        self.assertEqual(api_post.call_args_list[0].args[0], "/phone/uploadFile")
        self.assertEqual(
            api_post.call_args_list[0].args[1],
            {"id": "env-1", "fileUrl": "https://cdn.example/v.mp4"},
        )
        self.assertEqual(api_post.call_args_list[2].args[0], "/phone/uploadFile/result")
        self.assertEqual(api_post.call_args_list[3].args[0], "/shell/execute")

    @patch("publisher.gallery_phone.upload_resource_url_to_phone", return_value=GALLERY_REMOTE_PATH)
    def test_same_env_and_url_uploads_once(self, upload):
        first = ensure_resource_on_gallery("env-1", "https://cdn.example/v.mp4")
        second = ensure_resource_on_gallery("env-1", "https://cdn.example/v.mp4")
        other = ensure_resource_on_gallery("env-2", "https://cdn.example/v.mp4")
        self.assertEqual(first, second)
        self.assertEqual(upload.call_count, 2)
        self.assertEqual(other, GALLERY_REMOTE_PATH)


class PhoneBootTests(SimpleTestCase):
    @patch("publisher.gallery_phone.time.sleep")
    @patch("publisher.gallery_phone.start_cloud_phone")
    @patch("publisher.gallery_phone.check_phone_status")
    def test_starting_phone_waits_instead_of_failing_start(self, status, start, _sleep):
        status.side_effect = [
            {"is_running": False, "status": 1},
            {"is_running": False, "status": 1},
            {"is_running": True, "status": 0},
        ]
        ensure_phone_running("env-1")
        start.assert_not_called()
        self.assertGreaterEqual(status.call_count, 3)

    @patch("publisher.gallery_phone.time.sleep")
    @patch("publisher.gallery_phone.start_cloud_phone", side_effect=RuntimeError("busy"))
    @patch("publisher.gallery_phone.check_phone_status")
    def test_start_error_still_waits_if_phone_is_starting(self, status, start, _sleep):
        status.side_effect = [
            {"is_running": False, "status": 2},
            {"is_running": False, "status": 1},
            {"is_running": True, "status": 0},
        ]
        ensure_phone_running("env-1")
        start.assert_called_once_with("env-1")


class AddTaskRoutingTests(SimpleTestCase):
    @override_settings(GEELARK_PUBLISH_MODE="gallery", GEELARK_TOKEN="tok")
    @patch("publisher.youtube_gallery.add_youtube_gallery_task", return_value="gal-1")
    def test_gallery_youtube_skips_stock_template(self, gallery_add):
        with patch("publisher.utils.requests.post") as post:
            task_id = add_youtube_task(
                env_id="env",
                resource_url="https://storage.example/v.mp4",
                schedule_at=1,
                title="My title",
                description="Full description",
            )
        self.assertEqual(task_id, "gal-1")
        gallery_add.assert_called_once()
        post.assert_not_called()

    @override_settings(GEELARK_PUBLISH_MODE="gallery", GEELARK_TOKEN="tok")
    @patch("publisher.tiktok_gallery.add_tiktok_gallery_task", return_value="gal-tt")
    def test_gallery_tiktok_skips_task_add(self, gallery_add):
        with patch("publisher.utils.requests.post") as post:
            task_id = add_tiktok_task("env", "https://storage.example/v.mp4", 1, "cap")
        self.assertEqual(task_id, "gal-tt")
        gallery_add.assert_called_once()
        post.assert_not_called()

    @override_settings(GEELARK_PUBLISH_MODE="gallery", GEELARK_TOKEN="tok")
    @patch("publisher.instagram_gallery.add_instagram_gallery_task", return_value="gal-ig")
    def test_gallery_instagram_skips_stock_reels(self, gallery_add):
        with patch("publisher.utils.requests.post") as post:
            task_id = add_instagram_task("env", "https://storage.example/v.mp4", 1, "cap")
        self.assertEqual(task_id, "gal-ig")
        gallery_add.assert_called_once()
        post.assert_not_called()

    @override_settings(GEELARK_PUBLISH_MODE="stock", GEELARK_YOUTUBE_PUBLISH_MODE="stock", GEELARK_TOKEN="tok")
    @patch("publisher.utils.requests.post")
    def test_stock_mode_still_calls_youtube_pub_short(self, post):
        post.return_value.status_code = 200
        post.return_value.raise_for_status = lambda: None
        post.return_value.json.return_value = {"code": 0, "data": {"taskId": "t1"}}
        task_id = add_youtube_task(
            env_id="env",
            resource_url="https://storage.example/v.mp4",
            schedule_at=1,
            title="My title",
            description="Full description",
        )
        self.assertEqual(task_id, "t1")
        self.assertIn("youtubePubShort", post.call_args.args[0])

    @override_settings(GEELARK_PUBLISH_MODE="gallery", GEELARK_TOKEN="tok")
    @patch("publisher.youtube_gallery.ensure_youtube_gallery_flow_id", return_value="yf")
    @patch("publisher.tiktok_gallery.ensure_tiktok_gallery_flow_id", return_value="tf")
    @patch("publisher.gallery_rpa._geelark_api_post")
    @patch(
        "publisher.gallery_phone.upload_resource_url_to_phone",
        return_value=GALLERY_REMOTE_PATH,
    )
    def test_youtube_then_tiktok_share_one_upload(self, upload, api_post, _tf, _yf):
        reset_gallery_push_cache()
        api_post.return_value = {"code": 0, "data": {"taskId": "rpa"}}
        add_youtube_task("env-1", "https://cdn.example/v.mp4", 1, "t")
        add_tiktok_task("env-1", "https://cdn.example/v.mp4", 1, "c")
        self.assertEqual(upload.call_count, 1)
        self.assertEqual(api_post.call_count, 2)


class SyncFalseSuccessTests(TestCase):
    def _task(self, network="YouTube", status="processing"):
        session = UploadSession.objects.create(name="sync-test")
        return PublicationTask.objects.create(
            session=session,
            profile_id="env-sync",
            social_network=network,
            video_url="https://example.com/v.mp4",
            comment="c",
            publish_time=timezone.now(),
            status=status,
            geelark_task_id="g-task-1",
        )

    @override_settings(GEELARK_VERIFY_RPA=True, GEELARK_VERIFY_YOUTUBE_RPA=True)
    @patch("publisher.views.stop_phone_if_idle", return_value=True)
    @patch("publisher.views.mark_phone_stopped")
    @patch("publisher.views.query_geelark_task_detail")
    @patch("publisher.views.query_geelark_task_statuses")
    def test_youtube_click_fail_status3_becomes_error(
        self, query_status, query_detail, mark_stopped, stop_idle
    ):
        task = self._task()
        query_status.return_value = {
            "g-task-1": {"status": 3, "cost": 442, "failCode": None}
        }
        query_detail.return_value = {"logs": PROD_FALSE_SUCCESS}

        sync_geelark_statuses([task.session], force=True)

        task.refresh_from_db()
        self.assertEqual(task.status, "error")
        self.assertEqual(task.geelark_fail_code, FAKE_SUCCESS_FAIL_CODE)
        self.assertIn("status=3", task.error_message)
        stop_idle.assert_called_once()
        query_detail.assert_called_once()

    @override_settings(GEELARK_VERIFY_RPA=True, GEELARK_VERIFY_YOUTUBE_RPA=True)
    @patch("publisher.views.stop_phone_if_idle", return_value=False)
    @patch("publisher.views.query_geelark_task_detail")
    @patch("publisher.views.query_geelark_task_statuses")
    def test_tiktok_click_fail_status3_becomes_error(self, query_status, query_detail, _stop):
        task = self._task(network="TikTok")
        query_status.return_value = {"g-task-1": {"status": 3, "cost": 100}}
        query_detail.return_value = {
            "logs": [
                "Click element: Selector: text：Post",
                "Click failed, please check whether the element exists:",
            ]
        }

        sync_geelark_statuses([task.session], force=True)

        task.refresh_from_db()
        self.assertEqual(task.status, "error")
        query_detail.assert_called_once()

    def test_resolve_helper_still_maps_false_success(self):
        status, code, message = resolve_completed_status("YouTube", PROD_FALSE_SUCCESS)
        self.assertEqual(status, "error")
        self.assertEqual(code, FAKE_SUCCESS_FAIL_CODE)
        self.assertIn("status=3", message)
