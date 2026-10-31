from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from django.utils import timezone

from common.testing import APITestCase
from jobqueue.models import JobServer, JobServerAddress, route_order
from networks.models import Network, NetworkType
from osmanagement.models import OSRepo
from systems.models import SystemImage


class RouteOrderTestCase(APITestCase):
  """ An IB network, a job server on it with a high load, and one off it with a low load (#254). """

  def setUp(self):
    super().setUp()
    net_type = NetworkType.objects.create(name="Ethernet")
    self.ib = Network.objects.create(name="ib", net_type=net_type, subnet="10.20.0.0", netmask=24)
    self.near = JobServer.objects.create(name="near", address="10.20.0.5", one_minute_load=0.9)
    self.far = JobServer.objects.create(name="far", address="192.168.1.5", one_minute_load=0.1)

  def order(self, client):
    return [s.name for s in route_order(JobServer.objects.all(), client)]

  def stale(self, model, **filters):
    model.objects.filter(**filters).update(heartbeat_time=timezone.now() - timedelta(minutes=2))


class RouteOrderTests(RouteOrderTestCase):

  def test_the_clients_network_comes_before_load(self):
    self.assertEqual(self.order("10.20.0.77"), ["near", "far"])

  def test_by_load_off_any_network(self):
    for client in ("192.0.2.1", "2001:db8::1", "", None, "not-an-ip"):
      with self.subTest(client=client):
        self.assertEqual(self.order(client), ["far", "near"])

  def test_a_registered_address_on_the_clients_network_counts(self):
    JobServerAddress.objects.create(jobserver=self.far, address="10.20.0.6", network=self.ib)
    servers = route_order(JobServer.objects.all(), "10.20.0.77")
    self.assertEqual([(s.name, s.route_address) for s in servers], [("far", "10.20.0.6"), ("near", "10.20.0.5")])

  def test_a_stale_registered_address_doesnt_count(self):
    JobServerAddress.objects.create(jobserver=self.far, address="10.20.0.6", network=self.ib)
    self.stale(JobServerAddress, address="10.20.0.6")
    servers = route_order(JobServer.objects.all(), "10.20.0.77")
    self.assertEqual([(s.name, s.route_address) for s in servers], [("near", "10.20.0.5"), ("far", "192.168.1.5")])

  def test_a_host_name_isnt_on_any_network(self):
    JobServer.objects.filter(pk=self.near.pk).update(address="near.example")
    self.assertEqual(self.order("10.20.0.77"), ["far", "near"])

  def test_unresponsive_job_servers_are_left_out(self):
    self.stale(JobServer, pk=self.near.pk)
    self.assertEqual(self.order("10.20.0.77"), ["far"])

  def test_unknown_load_goes_last(self):
    JobServer.objects.filter(pk=self.far.pk).update(one_minute_load=None)
    self.assertEqual(self.order("192.0.2.1"), ["near", "far"])

  def test_ties_are_in_random_order(self):
    JobServer.objects.filter(pk=self.near.pk).update(one_minute_load=0.1)
    firsts = {self.order("192.0.2.1")[0] for _ in range(50)}
    self.assertEqual(firsts, {"near", "far"})


class RouteOrderRedirectTests(RouteOrderTestCase):
  """ /images/ and /osrepos/ redirect by route_order(). """

  def setUp(self):
    super().setUp()
    self.client.logout()
    self.image = SystemImage.objects.create(name="compute", created_by=self.user, needs_rebuild=False)
    self.image.jobservers.add(self.near, self.far)
    self.repo = OSRepo.objects.create(name="baseos", repo_package_url="http://mirror/baseos", managed=True)
    self.repo.hosted_by.add(self.near, self.far)
    patcher = mock.patch("systems.views_noauth.requests.head", return_value=SimpleNamespace(status_code=200))
    patcher.start()
    self.addCleanup(patcher.stop)

  def test_image_redirect(self):
    for client, host in (("10.20.0.77", "10.20.0.5"), ("192.0.2.1", "192.168.1.5")):
      with self.subTest(client=client):
        response = self.client.get("/images/compute/", REMOTE_ADDR=client)
        self.assertEqual(response["Location"], f"http://{host}:8080/images/compute/compute.img")

  def test_repo_redirect_is_least_loaded_not_random(self):
    for client, host in (("10.20.0.77", "10.20.0.5"), ("192.0.2.1", "192.168.1.5")):
      with self.subTest(client=client):
        for _ in range(10):
          response = self.client.get(f"/osrepos/{self.repo.pk}/repodata/repomd.xml", REMOTE_ADDR=client)
          self.assertEqual(response["Location"], f"http://{host}:8080/repos/{self.repo.pk}/repodata/repomd.xml")
