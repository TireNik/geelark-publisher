from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from publisher.models import PublicationTask, UploadSession
from publisher.phone_guard import running_rpa_count


def _task(session, profile_id, *, status='prepared', geelark_task_id='', **kwargs):
    defaults = {
        'session': session,
        'profile_id': profile_id,
        'social_network': 'YouTube',
        'video_url': f'https://cdn.example/{profile_id}.mp4',
        'comment': 'c',
        'publish_time': timezone.now(),
        'status': status,
        'resource_url': f'https://oss.example/{profile_id}.mp4',
        'geelark_task_id': geelark_task_id,
    }
    defaults.update(kwargs)
    return PublicationTask.objects.create(**defaults)


class RunningRpaCountTests(TestCase):
    def setUp(self):
        self.session = UploadSession.objects.create(name='rpa-count')

    def test_counts_live_rpa_across_profiles(self):
        _task(self.session, 'env-a', status='processing', geelark_task_id='gl-1')
        _task(self.session, 'env-b', status='submitted', geelark_task_id='gl-2')
        _task(self.session, 'env-c', status='prepared')
        self.assertEqual(running_rpa_count(), 2)

    def test_fresh_sending_counts(self):
        sending = _task(self.session, 'env-a', status='sending', geelark_task_id='')
        sending.processed_at = timezone.now()
        sending.save(update_fields=['processed_at'])
        self.assertEqual(running_rpa_count(), 1)


class DispatchParallelCapTests(TestCase):
    def setUp(self):
        self.session = UploadSession.objects.create(name='dispatch-cap')

    @override_settings(GEELARK_MAX_PARALLEL=2, GEELARK_DISPATCH_LEAD_SECONDS=120)
    @patch('publisher.management.commands.geelark_dispatch.u.create_geelark_publish_task')
    def test_three_prepared_starts_only_two(self, create_task):
        create_task.side_effect = lambda **kwargs: f"gl-{kwargs['env_id']}"
        a = _task(self.session, 'env-a')
        b = _task(self.session, 'env-b')
        c = _task(self.session, 'env-c')

        call_command('geelark_dispatch')

        a.refresh_from_db()
        b.refresh_from_db()
        c.refresh_from_db()
        statuses = {a.status, b.status, c.status}
        self.assertEqual(statuses, {'submitted', 'prepared'})
        self.assertEqual(sum(1 for t in (a, b, c) if t.status == 'submitted'), 2)
        self.assertEqual(sum(1 for t in (a, b, c) if t.status == 'prepared'), 1)
        self.assertEqual(create_task.call_count, 2)

    @override_settings(GEELARK_MAX_PARALLEL=2, GEELARK_DISPATCH_LEAD_SECONDS=120)
    @patch('publisher.management.commands.geelark_dispatch.u.create_geelark_publish_task')
    def test_full_slot_leaves_prepared_queued(self, create_task):
        create_task.side_effect = AssertionError('must not start a third phone')
        _task(self.session, 'env-a', status='processing', geelark_task_id='gl-1')
        _task(self.session, 'env-b', status='processing', geelark_task_id='gl-2')
        queued = _task(self.session, 'env-c')

        call_command('geelark_dispatch')

        queued.refresh_from_db()
        self.assertEqual(queued.status, 'prepared')
        create_task.assert_not_called()
