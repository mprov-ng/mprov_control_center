from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase

from systems.models import SystemImage


class ImagesAPIViewJobserverTests(TestCase):
  """ /images/<pk>/ picks a job server the client can resolve and reach. """

  def setUp(self):
    from jobqueue.models import JobServer
    user = User.objects.create(username="images-test")
    self.image = SystemImage.objects.create(name="compute", created_by=user, needs_rebuild=False)
    self.bad = JobServer.objects.create(name="bad", address="bad.example", one_minute_load=0.1)
    self.good = JobServer.objects.create(name="good", address="good.example", one_minute_load=0.5)
    self.ip = JobServer.objects.create(name="ip", address="10.0.0.3", one_minute_load=0.9)
    self.image.jobservers.add(self.bad, self.good, self.ip)
    patcher = mock.patch("systems.views_noauth.dns.resolver.resolve", side_effect=self.resolve)
    patcher.start()
    self.addCleanup(patcher.stop)

  @staticmethod
  def resolve(name, rdtype, search=True):
    if name == "good.example":
      return SimpleNamespace(rrset=["10.0.0.2"])
    raise Exception(f"NXDOMAIN {name}")

  def test_unresolvable_jobservers_are_skipped(self):
    from systems.views_noauth import ImagesAPIView
    self.assertEqual(ImagesAPIView().getJobserver(self.image, "10.0.0.50"), [self.good, self.ip])

  def test_no_resolvable_jobserver_is_404(self):
    from rest_framework.exceptions import NotFound
    from systems.views_noauth import ImagesAPIView
    self.image.jobservers.remove(self.good, self.ip)
    with self.assertRaises(NotFound):
      ImagesAPIView().getJobserver(self.image, "10.0.0.50")

  @mock.patch("systems.views_noauth.requests.head")
  def test_unreachable_jobserver_is_removed_from_the_image(self, head):
    head.side_effect = lambda url, timeout: SimpleNamespace(status_code=500 if "good.example" in url else 200)
    response = self.client.get("/images/compute/", REMOTE_ADDR="10.0.0.50")
    self.assertEqual(response.status_code, 302)
    self.assertEqual(response["Location"], "http://10.0.0.3:8080/images/compute/compute.img")
    # bad.example didn't resolve for this client, but it may serve others.
    self.assertEqual(sorted(js.name for js in self.image.jobservers.all()), ["bad", "ip"])
