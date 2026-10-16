from unittest import mock

from rest_framework.request import Request
from rest_framework.response import Response

from common.testing import APITestCase
from jobqueue.models import Job, JobModule, JobStatus
from jobqueue.views import JobAPIView


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


class JobDetailTests(APITestCase):
  """ GET /jobs/<pk>/ returns the job. """

  def test_job_detail(self):
    module = JobModule.objects.create(slug="pxe-update", name="PXE Update")
    status = JobStatus.objects.create(name="Pending")
    job = Job.objects.create(name="PXE Update", module=module, status=status)
    response = self.get_json(f"/jobs/{job.pk}/")
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json()["id"], job.pk)

  def test_retrieve_gets_the_request(self):
    # retrieve(request, ...), not retrieve(self, request, ...).
    with mock.patch.object(JobAPIView, "retrieve", autospec=True, return_value=Response(None)) as retrieve:
      self.get_json("/jobs/1/")
    view, request = retrieve.call_args.args
    self.assertIsInstance(view, JobAPIView)
    self.assertIsInstance(request, Request)
    self.assertEqual(retrieve.call_args.kwargs, {"pk": 1})
