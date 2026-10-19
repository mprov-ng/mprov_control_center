import json

from common.testing import APITestCase
from jobqueue.models import JobModule


class JobQueueURLTests(APITestCase):
  """ /jobqueue/<pk>/ takes a job module slug, and doesn't hide status-changes/. """

  def test_job_module_detail_by_slug(self):
    JobModule.objects.create(slug="pxe-update", name="PXE Update")
    response = self.get_json("/jobqueue/pxe-update/")
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json()["slug"], "pxe-update")

  def test_status_changes_still_routed(self):
    response = self.get_json("/jobqueue/status-changes/")
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json(), {"changes": []})
