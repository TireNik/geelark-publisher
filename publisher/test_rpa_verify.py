from django.test import SimpleTestCase

from publisher.rpa_verify import classify_completed_rpa, youtube_rpa_is_false_success


PROD_FALSE_SUCCESS = [
    "[2026-08-27 12:40:05 369] Click element: Selector condition: Equal  Selector: text：Upload Short",
    "[2026-08-27 12:40:08 378] Click failed, please check whether the element exists:",
    "[2026-08-27 12:40:41 406] Wait for element to appear: Selector: text：Uploaded to Your Videos  Waiting time: 1000",
    "[2026-08-27 12:42:45 885] Close app: Package name: com.google.android.youtube",
]

PROD_NEXT_BUTTON_FALSE_SUCCESS = [
    "[2026-08-28 06:15:47 651] Click element: Selector: id：com.google.android.youtube:id/shorts_camera_next_button",
    "[2026-08-28 06:15:52 665] Click failed, please check whether the element exists:",
    "[2026-08-28 06:16:12 643] Wait for element to appear: Selector: text：Upload Short  Waiting time: 5000",
    "[2026-08-28 06:18:09 668] Wait for element to appear: Selector: text：Uploaded to Your Videos  Waiting time: 1000",
    "[2026-08-28 06:20:14 973] Close app: Package name: com.google.android.youtube",
    "[2026-08-28 06:20:18 580] Run successfully:",
]

CLEAN_SUCCESS = [
    "[2026-08-24 15:01:18 739] Click element: Selector: id：com.google.android.youtube:id/shorts_camera_next_button",
    "[2026-08-24 15:01:35 321] Wait for element to appear: Selector: text：Upload Short",
    "[2026-08-24 15:01:42 785] Click element: Selector: text：Upload Short",
    "[2026-08-24 15:01:44 983] Wait for element to appear: Selector: text：Uploaded to Your Videos  Waiting time: 1000",
    "[2026-08-24 15:03:49 263] Close app: Package name: com.google.android.youtube",
]

PROD_NO_ELEMENT_FALSE_SUCCESS = [
    "[2026-08-28 09:51:07 730] Click element: Selector: text：Next  Waiting time: 20000",
    "[2026-08-28 09:51:27 805] No element found. Check whether the element properties are filled in properly or whether the current page contains an element:",
    "[2026-08-28 09:52:43 104] Click element: Selector: text：Upload Short  Waiting time: 15000",
    "[2026-08-28 09:52:58 153] No element found. Check whether the element properties are filled in properly or whether the current page contains an element:",
    "[2026-08-28 09:54:15 610] Run successfully:",
]


class YoutubeRpaVerifyTests(SimpleTestCase):
    def test_prod_click_failed_upload_short_is_false_success(self):
        self.assertTrue(youtube_rpa_is_false_success(PROD_FALSE_SUCCESS))
        self.assertEqual(
            classify_completed_rpa("YouTube", PROD_FALSE_SUCCESS),
            "false_success",
        )

    def test_prod_click_failed_next_resource_id_is_false_success(self):
        self.assertTrue(youtube_rpa_is_false_success(PROD_NEXT_BUTTON_FALSE_SUCCESS))
        self.assertEqual(
            classify_completed_rpa("YouTube", PROD_NEXT_BUTTON_FALSE_SUCCESS),
            "false_success",
        )

    def test_clean_youtube_logs_are_success(self):
        self.assertFalse(youtube_rpa_is_false_success(CLEAN_SUCCESS))
        self.assertEqual(classify_completed_rpa("YouTube", CLEAN_SUCCESS), "success")

    def test_no_element_found_on_upload_is_false_success(self):
        self.assertTrue(youtube_rpa_is_false_success(PROD_NO_ELEMENT_FALSE_SUCCESS))
        self.assertEqual(
            classify_completed_rpa("YouTube", PROD_NO_ELEMENT_FALSE_SUCCESS),
            "false_success",
        )

    def test_tiktok_post_click_fail_is_false_success(self):
        logs = [
            "Click element: Selector: text：Post",
            "Click failed, please check whether the element exists:",
        ]
        self.assertEqual(classify_completed_rpa("TikTok", logs), "false_success")

    def test_paste_click_fail_without_publish_button_is_ok(self):
        logs = [
            "Click element: Selector: text：Paste",
            "Click failed, please check whether the element exists:",
        ]
        self.assertFalse(youtube_rpa_is_false_success(logs))


    def test_next_click_fail_then_post_button_is_success(self):
        """Working stock path: Next Click-failed, then shorts_post_bottom_button."""
        logs = [
            "Click element: Selector: id：com.google.android.youtube:id/shorts_camera_next_button",
            "Click failed, please check whether the element exists:",
            "Click element: Selector: id：com.google.android.youtube:id/shorts_post_bottom_button",
            "Wait for element to appear: Selector: text：Uploaded to Your Videos",
            "Run successfully:",
        ]
        self.assertFalse(youtube_rpa_is_false_success(logs))
        self.assertEqual(classify_completed_rpa("YouTube", logs), "success")

    def test_resolve_completed_status_maps_fields(self):
        from publisher.rpa_verify import FAKE_SUCCESS_FAIL_CODE, resolve_completed_status

        status, code, message = resolve_completed_status("YouTube", PROD_FALSE_SUCCESS)
        self.assertEqual(status, "error")
        self.assertEqual(code, FAKE_SUCCESS_FAIL_CODE)
        self.assertIn("status=3", message)
        ok_status, ok_code, ok_msg = resolve_completed_status("YouTube", CLEAN_SUCCESS)
        self.assertEqual(ok_status, "success")
        self.assertIsNone(ok_code)
        self.assertEqual(ok_msg, "")
