from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from django.utils import timezone

from common.testing import APITestCase
from jobqueue.models import JobServer
from osmanagement.models import OSRepo
from systems.models import SystemImage


class StaleJobServerTestCase(APITestCase):
  """ Two job servers hosting an image and a repo; js1 has the lower load (#254). """

  def setUp(self):
    super().setUp()
    self.js1 = JobServer.objects.create(name="js1", address="10.0.0.1", one_minute_load=0.1)
    self.js2 = JobServer.objects.create(name="js2", address="10.0.0.2", one_minute_load=0.9)
    self.image = SystemImage.objects.create(name="compute", created_by=self.user, needs_rebuild=False)
    self.image.jobservers.add(self.js1, self.js2)
    self.repo = OSRepo.objects.create(name="baseos", repo_package_url="http://mirror/baseos", managed=True)
    self.repo.hosted_by.add(self.js1, self.js2)

  def unresponsive(self, *servers):
    JobServer.objects.filter(pk__in=[s.pk for s in servers]).update(heartbeat_time=timezone.now() - timedelta(minutes=2))


class StaleJobServerRoutingTests(StaleJobServerTestCase):
  """ /images/ and /osrepos/ skip unresponsive job servers, which stay on the image and repo. """

  def setUp(self):
    super().setUp()
    self.client.logout()
    patcher = mock.patch("systems.views_noauth.requests.head", return_value=SimpleNamespace(status_code=200))
    patcher.start()
    self.addCleanup(patcher.stop)

  def test_image_redirect_skips_an_unresponsive_server(self):
    self.unresponsive(self.js1)
    response = self.client.get("/images/compute/", REMOTE_ADDR="192.0.2.1")
    self.assertEqual(response["Location"], "http://10.0.0.2:8080/images/compute/compute.img")
    self.assertEqual(set(self.image.jobservers.all()), {self.js1, self.js2})

  def test_image_404_when_none_are_responsive(self):
    self.unresponsive(self.js1, self.js2)
    response = self.client.get("/images/compute/", REMOTE_ADDR="192.0.2.1")
    self.assertEqual(response.status_code, 404)
    self.assertIn("No responsive", response.json()["detail"])

  def test_repo_redirect_skips_an_unresponsive_server(self):
    self.unresponsive(self.js2)
    for _ in range(5):
      response = self.client.get(f"/osrepos/{self.repo.pk}/repodata/repomd.xml", REMOTE_ADDR="192.0.2.1")
      self.assertEqual(response["Location"], f"http://10.0.0.1:8080/repos/{self.repo.pk}/repodata/repomd.xml")
    self.assertEqual(set(self.repo.hosted_by.all()), {self.js1, self.js2})

  def test_repo_404_when_none_are_responsive(self):
    self.unresponsive(self.js1, self.js2)
    response = self.client.get(f"/osrepos/{self.repo.pk}/repodata/repomd.xml", REMOTE_ADDR="192.0.2.1")
    self.assertEqual(response.status_code, 404)


class StaleJobServerDisplayTests(StaleJobServerTestCase):
  """ The API and the admin show whether a job server is responsive. """

  def test_api_field(self):
    self.unresponsive(self.js2)
    servers = {s["name"]: s["responsive"] for s in self.get_json("/jobservers/").json()}
    self.assertEqual(servers, {"js1": True, "js2": False})
    self.assertFalse(self.get_json(f"/jobservers/{self.js2.pk}/").json()["responsive"])

  def test_admin_column_and_filter(self):
    self.unresponsive(self.js2)
    page = self.client.get("/admin/jobqueue/jobserver/")
    self.assertContains(page, "Responsive")
    for value, shown, hidden in (("yes", "js1", "js2"), ("no", "js2", "js1")):
      with self.subTest(responsive=value):
        page = self.client.get(f"/admin/jobqueue/jobserver/?responsive={value}")
        self.assertContains(page, f">{shown}<")
        self.assertNotContains(page, f">{hidden}<")
