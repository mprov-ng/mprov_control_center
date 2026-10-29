from jobqueue.models import Job, JobModule, JobStatus
from networks.testing import NetworkTestCase
from systems.models import System, NetworkInterface, SystemBMC


class UnknownQueryParamTests(NetworkTestCase):
  """ A list GET answers 400 for a query key it doesn't filter on, instead of returning every row (#390). """

  def setUp(self):
    super().setUp()
    self.lan.isdhcp = True
    self.lan.managedns = True
    self.lan.save()
    self.switch("sw1", self.lan)
    self.system = System.objects.create(hostname="node01", created_by=self.user)
    NetworkInterface.objects.create(system=self.system, name="eth0", hostname="node01", network=self.lan,
                                    ipaddress="172.16.0.11")
    SystemBMC.objects.create(system=self.system, ipaddress="10.0.1.11", network=self.mgmt)
    JobStatus.objects.create(pk=1, name="PENDING")
    for slug in ("dns-update", "repo-update", "image-update"):
      JobModule.objects.create(slug=slug, name=slug)
    Job.objects.create(name="DNS", module_id="dns-update", status_id=1)
    Job.objects.create(name="Image", module_id="image-update", status_id=1, params={"imageId": "compute"})

  def assert_400(self, url, key, message):
    response = self.get_json(url)
    self.assertEqual(response.status_code, 400, url)
    self.assertIn(message, response.json()[key])

  def test_unknown_key_is_400(self):
    for url, key in (("/systems/?hostnme=node01", "hostnme"), ("/networks/?nmae=Mgmt", "nmae"),
                     ("/networks/?isdhcp=true&nmae=Mgmt", "nmae"), ("/switches/?network=cluster-lan&nmae=sw1", "nmae"),
                     ("/networkinterfaces/?nmae=eth0", "nmae"), ("/systembmcs/?sytem=1", "sytem"),
                     ("/jobmodules/?nmae=x", "nmae"), ("/jobs/?stauts=1", "stauts")):
      self.assert_400(url, key, "Field doesn't exist.")

  def test_lookup_is_400(self):
    self.assert_400("/systems/?hostname__startswith=node", "hostname__startswith", "lookups (__) are not supported")
    self.assert_400("/jobs/?status__in=1", "status__in", "lookups (__) are not supported")

  def test_bare_json_job_query_is_400(self):
    # mprov_jobserver 0.0.62 with imageList set sends jobs/?{"imageId":...},
    # which used to match every job.
    response = self.get_json('/jobs/?{"imageId":"compute"}')
    self.assertEqual(response.status_code, 400)

  def test_keys_the_clients_send(self):
    # every list query the jobserver, mprov_scripts, mash and the mPCC's own
    # node scripts send, as of jobserver 0.0.62 and main.
    for url in ("/networks/?isdhcp=True", "/networks/?managedns=True",
                "/networkinterfaces/?network=cluster-lan", "/networkinterfaces/?hostname=node01",
                f"/networkinterfaces/?system={self.system.id}",
                "/switches/?network=cluster-lan",
                f"/systembmcs/?network={self.mgmt.id}&detail", f"/systembmcs/?system={self.system.id}&detail",
                "/systems/?hostname=node01", "/systems/?detail",
                "/jobs/?search=dns-update", '/jobs/?&module=["dns-update","dns-delete"]&status=1',
                '/jobs/?jobserver=1&module=image-update&params={"imageId":"compute"}&status=2',
                "/jobs/?&module=repo-update&status=1",
                "/jobmodules/?detail", "/jobmodules/?search=dns", "/jobmodules/?format=json"):
      self.assertEqual(self.get_json(url).status_code, 200, url)

  def test_self(self):
    response = self.client.get("/systems/?self", CONTENT_TYPE="application/json", REMOTE_ADDR="172.16.0.11")
    self.assertEqual(response.status_code, 200)
    self.assertEqual([s["hostname"] for s in response.json()], ["node01"])
