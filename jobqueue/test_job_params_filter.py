
from common.testing import APITestCase
from jobqueue.models import Job, JobModule, JobStatus


class JobParamsFilterTests(APITestCase):
  """ GET /jobs/?params={...} matches jobs by their params' keys. """

  def setUp(self):
    super().setUp()
    module = JobModule.objects.create(slug="repo-update", name="Update Repos")
    status = JobStatus.objects.create(pk=1, name="PENDING")
    for repo_id in (1, 2):
      Job.objects.create(name="Update Repos", module=module, status=status, params={"repo_id": repo_id, "x": "y"})

  def test_filter_by_params(self):
    response = self.client.get("/jobs/", {"params": '{"repo_id": 2}'}, CONTENT_TYPE="application/json")
    self.assertEqual(response.status_code, 200)
    self.assertEqual([job["params"]["repo_id"] for job in response.json()], [2])

  def test_filter_by_string_params(self):
    # issue #385: string values never matched on MariaDB.  How the jobserver
    # finds an image's image-update jobs.
    module = JobModule.objects.create(slug="image-update", name="Update Images")
    for slug in ("compute", "login"):
      Job.objects.create(name="Update Images", module=module, status_id=1, params={"imageId": slug})
    response = self.client.get("/jobs/", {"module": "image-update", "status": 1, "params": '{"imageId": "login"}'},
                               CONTENT_TYPE="application/json")
    self.assertEqual(response.status_code, 200)
    self.assertEqual([job["params"]["imageId"] for job in response.json()], ["login"])

  def test_filter_by_several_keys(self):
    response = self.client.get("/jobs/", {"params": '{"repo_id": 1, "x": "y"}'}, CONTENT_TYPE="application/json")
    self.assertEqual([job["params"]["repo_id"] for job in response.json()], [1])
    response = self.client.get("/jobs/", {"params": '{"repo_id": 1, "x": "z"}'}, CONTENT_TYPE="application/json")
    self.assertEqual(response.json(), [])

  def test_bad_params_is_400(self):
    for value in ("nope", "[1]"):
      response = self.client.get("/jobs/", {"params": value}, CONTENT_TYPE="application/json")
      self.assertEqual(response.status_code, 400, value)
