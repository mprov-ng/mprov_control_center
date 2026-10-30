import json
from types import SimpleNamespace
from unittest import mock

from common.testing import APITestCase
from jobqueue.models import JobServer, JobServerAddress
from networks.models import Network, NetworkType
from osmanagement.models import OSRepo
from systems.models import SystemImage


class JobServerAddressTestCase(APITestCase):
  """ Two networks and a helper to register a job server (mprov_jobserver#114). """

  def setUp(self):
    super().setUp()
    net_type = NetworkType.objects.create(name="Ethernet")
    self.lan = Network.objects.create(name="lan", net_type=net_type, subnet="172.16.0.0", netmask=16)
    self.ib = Network.objects.create(name="ib", net_type=net_type, subnet="10.20.0.0", netmask=24)

  def post(self, **data):
    body = {"name": "js1", "address": "192.168.1.5", "one_minute_load": 0.5, "jobmodules": [], **data}
    return self.client.post("/jobservers/", json.dumps(body), content_type="application/json")

  def addresses(self, server):
    return sorted((a.address, a.network_id) for a in server.addresses.all())


class JobServerAddressRegisterTests(JobServerAddressTestCase):
  """ POST /jobservers/ stores a job server's per-network addresses from each heartbeat. """

  def registered(self, response):
    self.assertEqual(response.status_code, 200, response.content)
    return JobServer.objects.get(pk=json.loads(response.json())["pk"])

  def test_addresses_are_stored_with_their_networks(self):
    server = self.registered(self.post(addresses=[
      {"address": "172.16.0.5", "network": self.lan.pk},
      # no network: found from the subnets.
      {"address": "10.20.0.5"},
      # a name or an address on no known network keeps no network.
      {"address": "js1.example"},
      {"address": "192.0.2.9"},
    ]))
    self.assertEqual(self.addresses(server), [("10.20.0.5", self.ib.pk), ("172.16.0.5", self.lan.pk),
                                              ("192.0.2.9", None), ("js1.example", None)])
    self.assertEqual(server.address, "192.168.1.5")

  def test_each_heartbeat_replaces_the_list(self):
    server = self.registered(self.post(addresses=[{"address": "172.16.0.5"}, {"address": "10.20.0.5"}]))
    self.registered(self.post(addresses=[{"address": "172.16.0.6"}]))
    self.assertEqual(self.addresses(server), [("172.16.0.6", self.lan.pk)])
    # without the list (an older job server), only the single address is left.
    self.registered(self.post())
    self.assertEqual(self.addresses(server), [])

  def test_bad_addresses_are_400_and_change_nothing(self):
    for addresses in ("172.16.0.5", [{"network": self.lan.pk}], [{"address": ""}], ["172.16.0.5"],
                      [{"address": "172.16.0.5", "network": 999}], [{"address": "172.16.0.5"}, {"address": "172.16.0.5"}]):
      with self.subTest(addresses=addresses):
        response = self.post(addresses=addresses)
        self.assertEqual(response.status_code, 400)
        self.assertIn("addresses", response.json())
    self.assertFalse(JobServer.objects.exists())

  def test_reply_lists_the_feature(self):
    response = self.post()
    self.assertIn("jobserver-addresses", json.loads(response.json())["features"])

  def test_admin_lists_the_addresses(self):
    server = self.registered(self.post(addresses=[{"address": "10.20.0.5"}]))
    page = self.client.get(f"/admin/jobqueue/jobserver/{server.pk}/change/")
    self.assertContains(page, "10.20.0.5")
    self.assertContains(page, "Job Server Address")


class JobServerAddressForTests(JobServerAddressTestCase):
  """ JobServer.address_for() picks the address on the client's network. """

  def setUp(self):
    super().setUp()
    self.server = JobServer.objects.create(name="js1", address="192.168.1.5")
    JobServerAddress.objects.create(jobserver=self.server, address="172.16.0.5", network=self.lan)
    JobServerAddress.objects.create(jobserver=self.server, address="10.20.0.5", network=self.ib)
    JobServerAddress.objects.create(jobserver=self.server, address="js1.example")

  def test_address_on_the_clients_network(self):
    self.assertEqual(self.server.address_for("10.20.0.77"), "10.20.0.5")
    self.assertEqual(self.server.address_for("172.16.9.9"), "172.16.0.5")

  def test_falls_back_to_the_single_address(self):
    for client in ("192.0.2.1", "2001:db8::1", "", None, "not-an-ip"):
      with self.subTest(client=client):
        self.assertEqual(self.server.address_for(client), "192.168.1.5")


class JobServerAddressRoutingTests(JobServerAddressTestCase):
  """ /images/ and /osrepos/ redirects send a client to the address on its network. """

  def setUp(self):
    super().setUp()
    self.client.logout()
    self.server = JobServer.objects.create(name="js1", address="192.168.1.5", port=8080)
    JobServerAddress.objects.create(jobserver=self.server, address="10.20.0.5", network=self.ib)
    self.image = SystemImage.objects.create(name="compute", created_by=self.user, needs_rebuild=False)
    self.image.jobservers.add(self.server)
    self.repo = OSRepo.objects.create(name="baseos", repo_package_url="http://mirror/baseos", managed=True)
    self.repo.hosted_by.add(self.server)
    patcher = mock.patch("systems.views_noauth.requests.head", return_value=SimpleNamespace(status_code=200))
    self.head = patcher.start()
    self.addCleanup(patcher.stop)

  def test_image_redirect(self):
    for client, host in (("10.20.0.77", "10.20.0.5"), ("192.0.2.1", "192.168.1.5")):
      with self.subTest(client=client):
        response = self.client.get("/images/compute/", REMOTE_ADDR=client)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"http://{host}:8080/images/compute/compute.img")

  def test_image_redirect_checks_the_routed_address(self):
    self.client.get("/images/compute.vmlinuz/", REMOTE_ADDR="10.20.0.77")
    self.head.assert_called_once_with("http://10.20.0.5:8080/images/compute/compute.vmlinuz", timeout=1)

  def test_repo_redirect(self):
    for client, host in (("10.20.0.77", "10.20.0.5"), ("192.0.2.1", "192.168.1.5")):
      with self.subTest(client=client):
        response = self.client.get(f"/osrepos/{self.repo.pk}/repodata/repomd.xml", REMOTE_ADDR=client)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"http://{host}:8080/repos/{self.repo.pk}/repodata/repomd.xml")
