from django.contrib.auth.models import User

from common.testing import APITestCase


class JobQueueURLTests(APITestCase):
  """ /jobqueue/<pk>/ takes a job module slug, and doesn't hide status-changes/. """

  def test_status_changes_need_a_staff_login(self):
    self.client.logout()
    self.assertEqual(self.get_json("/jobqueue/status-changes/").status_code, 403)
    User.objects.create_user("user", password="password")
    self.client.login(username="user", password="password")
    self.assertEqual(self.get_json("/jobqueue/status-changes/").status_code, 403)
