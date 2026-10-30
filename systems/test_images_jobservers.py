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
  def test_unreachable_jobserver_is_skipped_not_removed(self, head):
    """Issue #321: one momentary fetch failure must not strip a jobserver."""
    head.side_effect = lambda url, timeout: SimpleNamespace(status_code=500 if "good.example" in url else 200)
    response = self.client.get("/images/compute/", REMOTE_ADDR="10.0.0.50")
    self.assertEqual(response.status_code, 302)
    self.assertEqual(response["Location"], "http://10.0.0.3:8080/images/compute/compute.img")
    # An unauthenticated GET may skip jobservers for this request only:
    # bad.example didn't resolve for this client and good.example 500'd,
    # but neither association may be deleted and saved.
    self.assertEqual(sorted(js.name for js in self.image.jobservers.all()), ["bad", "good", "ip"])

  @mock.patch("systems.views_noauth.requests.head")
  def test_no_responsive_jobserver_404s_without_stripping(self, head):
    """All fetches failing returns 404 but leaves every association intact."""
    head.side_effect = lambda url, timeout: SimpleNamespace(status_code=500)
    response = self.client.get("/images/compute/", REMOTE_ADDR="10.0.0.50")
    self.assertEqual(response.status_code, 404)
    self.assertEqual(sorted(js.name for js in self.image.jobservers.all()), ["bad", "good", "ip"])


class ImagesAPIViewIPv6Tests(TestCase):
  """ Issue #309: an IPv6 job server address is bracketed in image URLs. """

  def setUp(self):
    from jobqueue.models import JobServer
    user = User.objects.create(username="images-v6-test")
    self.image = SystemImage.objects.create(name="compute", created_by=user, needs_rebuild=False)
    self.v6 = JobServer.objects.create(name="v6", address="fd00::5", one_minute_load=0.1)
    self.image.jobservers.add(self.v6)

  def test_image_url_brackets_ipv6(self):
    from systems.views_noauth import ImagesAPIView
    self.assertEqual(ImagesAPIView.imageURL(self.v6, self.image), "http://[fd00::5]:8080/images/compute/compute.img")
    self.assertEqual(ImagesAPIView.imageURL(self.v6, self.image, isKernel=True), "http://[fd00::5]:8080/images/compute/compute.vmlinuz")
    self.assertEqual(ImagesAPIView.imageURL(self.v6, self.image, isInitRamFS=True), "http://[fd00::5]:8080/images/compute/compute.initramfs")

  def test_image_url_leaves_ipv4_and_names_alone(self):
    from systems.views_noauth import ImagesAPIView
    for address in ("10.0.0.3", "js.example", "[fd00::5]"):
      js = SimpleNamespace(address=address, port=8080)
      self.assertEqual(ImagesAPIView.imageURL(js, self.image), f"http://{address}:8080/images/compute/compute.img")

  @mock.patch("systems.views_noauth.requests.head")
  def test_redirect_to_ipv6_jobserver_is_bracketed(self, head):
    head.return_value = SimpleNamespace(status_code=200)
    for path, suffix in (("/images/compute/", ".img"), ("/images/compute.vmlinuz/", ".vmlinuz"), ("/images/compute.initramfs/", ".initramfs")):
      response = self.client.get(path, REMOTE_ADDR="fd00::50")
      self.assertEqual(response.status_code, 302, path)
      self.assertEqual(response["Location"], f"http://[fd00::5]:8080/images/compute/compute{suffix}")
      head.assert_called_with(f"http://[fd00::5]:8080/images/compute/compute{suffix}", timeout=1)
    # the bracketed form is never saved back to the job server.
    self.v6.refresh_from_db()
    self.assertEqual(self.v6.address, "fd00::5")
