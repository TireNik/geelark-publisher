from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from publisher.gallery_adb import (
    GALLERY_REMOTE_PATH,
    connect_and_login,
    get_adb_endpoint,
    push_to_gallery,
    youtube_gallery_mode_enabled,
)
from publisher.rpa_verify import FAKE_SUCCESS_FAIL_CODE, resolve_completed_status
from publisher.test_rpa_verify import PROD_FALSE_SUCCESS
from publisher.youtube_gallery import (
    add_youtube_gallery_task,
    build_youtube_gallery_flow,
    ensure_youtube_gallery_flow_id,
)
from publisher.models import PublicationTask, UploadSession
from publisher.views import sync_geelark_statuses
from publisher.utils import add_youtube_task


class YoutubeGalleryModeTests(SimpleTestCase):
    @override_settings(GEELARK_YOUTUBE_PUBLISH_MODE="stock")
    def test_stock_is_default_off(self):
        self.assertFalse(youtube_gallery_mode_enabled())

    @override_settings(GEELARK_YOUTUBE_PUBLISH_MODE="gallery")
    def test_gallery_flag(self):
        self.assertTrue(youtube_gallery_mode_enabled())


class YoutubeGalleryFlowTests(SimpleTestCase):
    def test_flow_stops_on_error_and_waits_for_upload(self):
        flow = build_youtube_gallery_flow()
        content = flow["content"]
        self.assertEqual(content["errorType"], "stop")
        dumped = str(content)
        self.assertIn("Upload Short", dumped)
        self.assertIn("Next", dumped)
        self.assertIn("Uploaded to Your Videos", dumped)
        self.assertNotIn("120000", dumped)
        waits = [
            step["config"].get("searchTime")
            for step in content["contents"]
            if step.get("type") == "waitEle"
            and any(
                f.get("content") == "Uploaded to Your Videos"
                for f in step["config"].get("filters", [])
            )
        ]
        self.assertEqual(waits, [60000])

    @override_settings(GEELARK_YOUTUBE_GALLERY_FLOW_ID="flow-fixed")
    def test_configured_flow_id_skips_import(self):
        self.assertEqual(ensure_youtube_gallery_flow_id(), "flow-fixed")

    @patch("publisher.youtube_gallery.push_resource_url_to_gallery")
    @patch("publisher.youtube_gallery.ensure_youtube_gallery_flow_id", return_value="flow-1")
    @patch("publisher.youtube_gallery._geelark_api_post")
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


class GalleryAdbTests(SimpleTestCase):
    @patch("publisher.gallery_adb._geelark_api_post")
    def test_get_adb_endpoint_retries_until_ready(self, api_post):
        api_post.side_effect = [
            {"code": 0, "data": {"items": [{"id": "e1", "code": 42002, "ip": "", "port": "", "pwd": ""}]}},
            {
                "code": 0,
                "data": {
                    "items": [
                        {"id": "e1", "code": 0, "ip": "1.2.3.4", "port": "21781", "pwd": "secret"}
                    ]
                },
            },
        ]
        with patch("publisher.gallery_adb.time.sleep"):
            endpoint = get_adb_endpoint("e1", attempts=3)
        self.assertEqual(endpoint["serial"], "1.2.3.4:21781")
        self.assertEqual(endpoint["pwd"], "secret")

    @patch("publisher.gallery_adb.subprocess.run")
    def test_connect_redacts_password_on_failure(self, run):
        run.side_effect = [
            SimpleNamespace(returncode=0, stdout="connected to 1.2.3.4:21781", stderr=""),
            SimpleNamespace(returncode=1, stdout="", stderr="glogin super-secret-pwd denied"),
        ]
        with self.assertRaises(RuntimeError) as ctx:
            connect_and_login(
                {"serial": "1.2.3.4:21781", "pwd": "super-secret-pwd"}
            )
        self.assertNotIn("super-secret-pwd", str(ctx.exception))
        self.assertIn("***", str(ctx.exception))

    @patch("publisher.gallery_adb._run_adb")
    def test_push_scans_media(self, run_adb):
        run_adb.return_value = SimpleNamespace(stdout="", stderr="", returncode=0)
        remote = push_to_gallery("1.2.3.4:1", MagicMock(__str__=lambda self: "/tmp/a.mp4"))
        self.assertEqual(remote, GALLERY_REMOTE_PATH)
        scan_args = run_adb.call_args_list[1].args[0]
        self.assertIn("android.intent.action.MEDIA_SCANNER_SCAN_FILE", scan_args)


class AddYoutubeTaskRoutingTests(SimpleTestCase):
    @override_settings(GEELARK_YOUTUBE_PUBLISH_MODE="gallery", GEELARK_TOKEN="tok")
    @patch("publisher.youtube_gallery.add_youtube_gallery_task", return_value="gal-1")
    def test_gallery_mode_skips_stock_template(self, gallery_add):
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

    @override_settings(GEELARK_YOUTUBE_PUBLISH_MODE="stock", GEELARK_TOKEN="tok")
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

    @override_settings(GEELARK_VERIFY_YOUTUBE_RPA=True)
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

    @override_settings(GEELARK_VERIFY_YOUTUBE_RPA=True)
    @patch("publisher.views.stop_phone_if_idle", return_value=False)
    @patch("publisher.views.query_geelark_task_detail")
    @patch("publisher.views.query_geelark_task_statuses")
    def test_tiktok_status3_skips_detail_fetch(self, query_status, query_detail, _stop):
        task = self._task(network="TikTok")
        query_status.return_value = {"g-task-1": {"status": 3, "cost": 100}}

        sync_geelark_statuses([task.session], force=True)

        task.refresh_from_db()
        self.assertEqual(task.status, "success")
        query_detail.assert_not_called()

    def test_resolve_helper_still_maps_false_success(self):
        status, code, message = resolve_completed_status("YouTube", PROD_FALSE_SUCCESS)
        self.assertEqual(status, "error")
        self.assertEqual(code, FAKE_SUCCESS_FAIL_CODE)
        self.assertIn("status=3", message)
