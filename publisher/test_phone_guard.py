from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from publisher.phone_guard import (
    is_zombie_running_task,
    max_parallel_jobs,
    profile_has_running_rpa,
    reap_zombie_running_tasks,
    sibling_keeps_phone,
    stop_phone_if_idle,
)
from publisher.session_runner import tasks_by_video_url


def _task(**kwargs):
    defaults = {
        'id': 1,
        'status': 'prepared',
        'publish_time': datetime(2026, 8, 20, 12, 0, 0),
        'geelark_task_id': '',
        'processed_at': None,
        'created_at': datetime(2026, 8, 20, 12, 0, 0),
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class SiblingKeepsPhoneTests(SimpleTestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 20, 12, 0, 0)
        self.lead = 120

    def test_single_network_success_does_not_keep(self):
        yt = _task(id=1, status='success')
        self.assertFalse(
            sibling_keeps_phone(yt, now=self.now, lead_seconds=self.lead, exclude_id=1)
        )

    def test_same_device_tiktok_prepared_due_now_keeps_phone(self):
        tt = _task(id=2, status='prepared', publish_time=self.now)
        self.assertTrue(
            sibling_keeps_phone(tt, now=self.now, lead_seconds=self.lead, exclude_id=1)
        )

    def test_scheduled_hours_later_does_not_keep_phone(self):
        later = self.now + timedelta(hours=3)
        tt = _task(id=2, status='prepared', publish_time=later)
        self.assertFalse(
            sibling_keeps_phone(tt, now=self.now, lead_seconds=self.lead, exclude_id=1)
        )

    def test_running_sibling_keeps_phone(self):
        other = _task(id=3, status='processing', geelark_task_id='gl-1')
        self.assertTrue(
            sibling_keeps_phone(other, now=self.now, lead_seconds=self.lead, exclude_id=1)
        )

    def test_zombie_sending_does_not_keep_phone(self):
        zombie = _task(id=4, status='sending', geelark_task_id='', processed_at=None)
        self.assertFalse(
            sibling_keeps_phone(zombie, now=self.now, lead_seconds=self.lead, exclude_id=1)
        )

    def test_exclude_self(self):
        self_task = _task(id=9, status='processing', geelark_task_id='gl-9')
        self.assertFalse(
            sibling_keeps_phone(self_task, now=self.now, lead_seconds=self.lead, exclude_id=9)
        )


class StopPhoneIfIdleTests(SimpleTestCase):
    @patch('publisher.phone_guard.stop_cloud_phone')
    @patch('publisher.phone_guard.profile_has_active_task', return_value=True)
    def test_does_not_stop_when_another_network_still_needs_phone(self, _has, stop):
        self.assertFalse(stop_phone_if_idle('env-1', exclude_task_id=10))
        stop.assert_not_called()

    @override_settings(GEELARK_DISPATCH_LEAD_SECONDS=120)
    @patch('publisher.phone_guard.stop_cloud_phone', return_value=True)
    @patch('publisher.phone_guard.check_phone_status', return_value={'is_running': True})
    @patch('publisher.phone_guard.profile_has_active_task', return_value=False)
    def test_stops_when_profile_is_idle(self, _has, _status, stop):
        self.assertTrue(stop_phone_if_idle('env-1', exclude_task_id=10))
        stop.assert_called_once_with('env-1')


class MaxParallelJobsTests(SimpleTestCase):
    @override_settings(GEELARK_MAX_PARALLEL=2)
    def test_default_cap_is_two(self):
        self.assertEqual(max_parallel_jobs(), 2)

    @override_settings(GEELARK_MAX_PARALLEL=0)
    def test_zero_becomes_one(self):
        self.assertEqual(max_parallel_jobs(), 1)

    @override_settings(GEELARK_MAX_PARALLEL=8)
    def test_no_hardcoded_three_clamp(self):
        self.assertEqual(max_parallel_jobs(), 8)


class ProfileHasRunningRpaTests(SimpleTestCase):
    def test_empty_profile(self):
        self.assertFalse(profile_has_running_rpa(''))

    @patch('publisher.phone_guard.PublicationTask.objects')
    def test_true_when_other_rpa_running(self, objects):
        objects.filter.return_value.filter.return_value.exclude.return_value.exists.return_value = True
        self.assertTrue(profile_has_running_rpa('env-1', exclude_id=10))

    @patch('publisher.phone_guard.PublicationTask.objects')
    def test_false_when_no_running_rpa(self, objects):
        objects.filter.return_value.filter.return_value.exists.return_value = False
        self.assertFalse(profile_has_running_rpa('env-1'))


class ZombieRunningTaskTests(SimpleTestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 24, 17, 0, 0)

    @override_settings(GEELARK_SENDING_ZOMBIE_SECONDS=600)
    def test_legacy_sending_without_stamp_is_zombie(self):
        zombie = _task(status='sending', geelark_task_id='', processed_at=None)
        self.assertTrue(is_zombie_running_task(zombie, now=self.now))

    @override_settings(GEELARK_SENDING_ZOMBIE_SECONDS=600)
    def test_fresh_sending_is_not_zombie(self):
        fresh = _task(
            status='sending',
            geelark_task_id='',
            processed_at=self.now - timedelta(seconds=30),
        )
        self.assertFalse(is_zombie_running_task(fresh, now=self.now))

    @override_settings(GEELARK_SENDING_ZOMBIE_SECONDS=600)
    def test_stale_sending_is_zombie(self):
        stale = _task(
            status='sending',
            geelark_task_id='',
            processed_at=self.now - timedelta(minutes=20),
        )
        self.assertTrue(is_zombie_running_task(stale, now=self.now))

    def test_with_geelark_id_is_not_zombie(self):
        live = _task(status='submitted', geelark_task_id='633', processed_at=None)
        self.assertFalse(is_zombie_running_task(live, now=self.now))

    @patch('publisher.phone_guard.refresh_session_status')
    @patch('publisher.phone_guard.PublicationTask.objects')
    def test_reap_marks_zombies_error(self, objects, refresh):
        session = SimpleNamespace(id=38)
        zombie = SimpleNamespace(
            id=459,
            session_id=38,
            session=session,
            status='sending',
            geelark_task_id='',
            processed_at=None,
            error_message='',
        )

        def save(*, update_fields=None):
            return None

        zombie.save = save
        qs = SimpleNamespace(
            filter=lambda *a, **k: qs,
            select_related=lambda *a, **k: [zombie],
        )
        objects.filter.return_value = qs

        self.assertEqual(reap_zombie_running_tasks(now=self.now), 1)
        self.assertEqual(zombie.status, 'error')
        refresh.assert_called_once_with(session)


class StorageReuseTests(SimpleTestCase):
    def test_excel_and_vf_same_url_share_one_prepare(self):
        yt = SimpleNamespace(id=1, video_url='https://vf.example/jobs/1/final?token=a')
        tt = SimpleNamespace(id=2, video_url='https://vf.example/jobs/1/final?token=a')
        ig = SimpleNamespace(id=3, video_url='https://vf.example/jobs/2/final?token=b')
        grouped = tasks_by_video_url([yt, tt, ig])
        self.assertEqual(len(grouped), 2)
        self.assertEqual({t.id for t in grouped[yt.video_url]}, {1, 2})
        self.assertEqual({t.id for t in grouped[ig.video_url]}, {3})
