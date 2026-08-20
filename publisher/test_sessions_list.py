from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from publisher.models import UploadSession
from publisher.views import SessionsListAPIView


class SessionsListAPIViewTests(TestCase):
    def test_returns_db_snapshot_without_calling_geelark(self):
        session = UploadSession.objects.create(name='Excel batch')
        factory = APIRequestFactory()
        request = factory.get('/api/sessions/')

        with patch('publisher.views.sync_geelark_statuses') as sync:
            response = SessionsListAPIView.as_view()(request)

        sync.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(len(response.data['sessions']), 1)
        self.assertEqual(response.data['sessions'][0]['id'], session.id)
        self.assertEqual(response.data['sessions'][0]['name'], 'Excel batch')
