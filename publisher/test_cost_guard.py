from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings

from publisher.cost_guard import (
    NOT_LOGGED_IN_CODE,
    PROXY_FAIL_CODE,
    remaining_task_ids,
    should_abort_session,
    skip_dispatch_reason,
)


class CostGuardDecisionTests(SimpleTestCase):
    def test_aborts_session_at_threshold(self):
        self.assertFalse(should_abort_session(2, threshold=3))
        self.assertTrue(should_abort_session(3, threshold=3))
        self.assertTrue(should_abort_session(11, threshold=3))

    def test_remaining_ids_skip_terminal_and_other_phones(self):
        tasks = [
            SimpleNamespace(id=1, status='prepared', profile_id='aaa'),
            SimpleNamespace(id=2, status='submitted', profile_id='aaa'),
            SimpleNamespace(id=3, status='success', profile_id='aaa'),
            SimpleNamespace(id=4, status='processing', profile_id='bbb'),
            SimpleNamespace(id=5, status='error', profile_id='aaa'),
        ]
        self.assertEqual(remaining_task_ids(tasks, exclude_id=1, profile_id='aaa'), [2])
        self.assertEqual(remaining_task_ids(tasks, exclude_id=1), [2, 4])

    def test_skip_dispatch_after_proxy_fail_on_same_phone(self):
        pairs = [(PROXY_FAIL_CODE, 'phone-a'), (20116, 'phone-b')]
        self.assertIsNotNone(skip_dispatch_reason('phone-a', pairs, threshold=3))
        self.assertIsNone(skip_dispatch_reason('phone-c', pairs, threshold=3))

    def test_skip_dispatch_after_not_logged_in_on_same_phone(self):
        pairs = [(NOT_LOGGED_IN_CODE, 'phone-a')]
        reason = skip_dispatch_reason('phone-a', pairs, threshold=3)
        self.assertIn('20116', reason)
        self.assertIsNone(skip_dispatch_reason('phone-b', pairs, threshold=3))

    def test_skip_dispatch_when_session_hits_proxy_batch(self):
        pairs = [
            (29996, 'p1'),
            (29996, 'p2'),
            (29996, 'p3'),
        ]
        reason = skip_dispatch_reason('p4', pairs, threshold=3)
        self.assertIn('29996', reason)

    @override_settings(GEELARK_PROXY_FAIL_ABORT_THRESHOLD=4)
    def test_threshold_from_settings(self):
        self.assertFalse(should_abort_session(3))
        self.assertTrue(should_abort_session(4))
