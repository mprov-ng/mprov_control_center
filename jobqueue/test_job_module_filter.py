from common.testing import APITestCase
from jobqueue.models import Job, JobModule, JobStatus


class JobModuleFilterTests(APITestCase):
  """ GET /jobs/?module= takes a job module ID or a JSON array of them. """

  def setUp(self):
    super().setUp()
    JobStatus.objects.create(pk=1, name="PENDING")
    for slug in ("dns-update", "pxe-update", "repo-update"):
      Job.objects.create(name=slug, module=JobModule.objects.create(slug=slug, name=slug), status_id=1)

  def modules(self, value):
    response = self.client.get("/jobs/", {"module": value}, CONTENT_TYPE="application/json")
    self.assertEqual(response.status_code, 200, value)
    return sorted(job["module"] for job in response.json())

  def test_one_module(self):
    self.assertEqual(self.modules("pxe-update"), ["pxe-update"])

  def test_array(self):
    # how the jobserver's dnsmasq plugin asks for its modules.
    self.assertEqual(self.modules('["dns-update","pxe-update"]'), ["dns-update", "pxe-update"])

  def test_empty_matches_nothing(self):
    # issue #328: was a 500 from IndexError.
    self.assertEqual(self.modules(""), [])

  def test_bad_array_is_400(self):
    # issue #328: bad JSON was a 500.
    for value in ("[nope", "[1]", '["dns-update", {}]'):
      response = self.client.get("/jobs/", {"module": value}, CONTENT_TYPE="application/json")
      self.assertEqual(response.status_code, 400, value)
      self.assertIn("module", response.json())
