import json

from common.testing import APITestCase
from jobqueue.models import Job, JobModule, JobServer, JobStatus
from networks.models import Network, NetworkType
from systems.models import NetworkInterface, System, SystemImage

PENDING, RUNNING, COMPLETE = 1, 2, 4


class ViewDetailHandlingTestCase(APITestCase):
  """ /systems/, /networks/ and /jobs/ serve details through MProvView (#298). """

  def setUp(self):
    super().setUp()
    self.net_type = NetworkType.objects.create(name="Ethernet")
    self.lan = Network.objects.create(name="lan", net_type=self.net_type, subnet="10.0.0.0", netmask=24, isdhcp=True)
    self.image = SystemImage.objects.create(name="compute", created_by=self.user, needs_rebuild=False)
    self.node = System.objects.create(hostname="node01", created_by=self.user, systemimage=self.image)
    NetworkInterface.objects.create(system=self.node, name="ens18", ipaddress="10.0.0.11", network=self.lan)
    for pk, name in ((PENDING, "PENDING"), (RUNNING, "RUNNING"), (COMPLETE, "COMPLETE")):
      JobStatus.objects.create(pk=pk, name=name)
    self.module = JobModule.objects.create(slug="dns-update", name="DNS Update")
    self.server = JobServer.objects.create(name="js1")
    self.job = Job.objects.create(name="DNS Update", module=self.module, status_id=RUNNING, jobserver=self.server)


class SystemDetailTests(ViewDetailHandlingTestCase):

  def test_single_system_is_nested(self):
    system = self.get_json(f"/systems/{self.node.pk}/").json()
    self.assertEqual(system["systemimage"]["slug"], "compute")

  def test_list_is_flat_and_detail_nested(self):
    self.assertEqual(self.get_json("/systems/").json()[0]["systemimage"], "compute")
    self.assertEqual(self.get_json("/systems/?detail").json()[0]["systemimage"]["slug"], "compute")

  def test_self_and_hostname_unchanged(self):
    response = self.client.get("/systems/?self", CONTENT_TYPE="application/json", REMOTE_ADDR="10.0.0.11")
    self.assertEqual(response.json()[0]["systemimage"]["slug"], "compute")
    self.assertEqual([s["hostname"] for s in self.get_json("/systems/?hostname=node").json()], ["node01"])
    self.assertEqual(self.get_json("/systems/?hostname=nope").status_code, 404)

  def test_writes_stay_flat(self):
    response = self.client.patch(f"/systems/{self.node.pk}/", json.dumps({"hostname": "node01b"}),
                                 content_type="application/json")
    self.assertEqual(response.status_code, 200, response.content)
    self.assertEqual(response.json()["systemimage"], "compute")


class NetworkDetailTests(ViewDetailHandlingTestCase):

  def test_single_network_is_nested(self):
    self.assertEqual(self.get_json(f"/networks/{self.lan.pk}/").json()["net_type"]["name"], "Ethernet")

  def test_list_is_flat_and_detail_nested(self):
    self.assertEqual(self.get_json("/networks/").json()[0]["net_type"], self.net_type.pk)
    self.assertEqual(self.get_json("/networks/?detail").json()[0]["net_type"]["name"], "Ethernet")

  def test_filters_unchanged(self):
    # the jobserver's dnsmasq plugins loop over these lists.
    self.assertEqual([n["name"] for n in self.get_json("/networks/?isdhcp=True").json()], ["lan"])
    self.assertEqual(self.get_json("/networks/?managedns=True").json(), [])
    self.assertEqual(self.get_json("/networks/?isdhcp=maybe").status_code, 400)


class JobDetailTests(ViewDetailHandlingTestCase):

  def test_single_job_stays_flat(self):
    # what mprov_jobserver's update_job_status() reads: status as an ID (#298).
    job = self.get_json(f"/jobs/{self.job.pk}/").json()
    self.assertEqual((job["status"], job["module"], job["jobserver"]), (RUNNING, "dns-update", self.server.pk))

  def test_list_is_flat_and_detail_nested(self):
    self.assertEqual(self.get_json("/jobs/").json()[0]["status"], RUNNING)
    job = self.get_json("/jobs/?detail").json()[0]
    self.assertEqual((job["status"]["name"], job["module"]["slug"], job["jobserver"]["name"]), ("RUNNING", "dns-update", "js1"))

  def test_filters_unchanged(self):
    self.assertEqual(len(self.get_json(f"/jobs/?jobserver={self.server.pk}&module=dns-update&status={RUNNING}").json()), 1)
    self.assertEqual(self.get_json("/jobs/?status=1").json(), [])
    self.assertEqual(self.get_json("/jobs/?detail&module=dns-update").json()[0]["module"]["slug"], "dns-update")
    self.assertEqual(self.get_json("/jobs/?nonsense=1").status_code, 400)
