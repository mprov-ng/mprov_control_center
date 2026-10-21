import json

from django.contrib.auth.models import User
from django.test import TestCase

from jobqueue.models import JobServer
from osmanagement.models import OSDistro, OSType
from osmanagement.serializers import OSDistroAPISerializer
from systems.models import System, SystemBMC, SystemImage
from systems.serializers import SystemImageSerializer


class DetailSerializerTests(TestCase):
  """ A GET with a primary key or ?detail nests relations.  It used to do that by
  setting Meta.depth on the shared serializer class, which leaked into every later
  request in the process: lists came back nested and writes to relations were
  silently dropped (#266).  /systemimages/<pk>/ never used its details serializer
  (#267). """

  def setUp(self):
    self.user = User.objects.create(username="detail-test")
    distro_args = dict(vendor="test", version="9", baseurl="http://localhost/", install_kernel_cmdline="quiet",
                       initial_mods="e1000", prov_interface="eth0", tmpfs_root_size=8)
    self.ostype = OSType.objects.create(slug="rhel", name="RHEL")
    self.distro = OSDistro.objects.create(name="distro-a", distType=self.ostype, **distro_args)
    self.other_distro = OSDistro.objects.create(name="distro-b", **distro_args)
    self.jobserver = JobServer.objects.create(name="js1")
    self.image = SystemImage.objects.create(name="detail-image", created_by=self.user, osdistro=self.distro)
    self.image.jobservers.add(self.jobserver)
    self.system = System.objects.create(hostname="detail-node", created_by=self.user, systemimage=self.image)
    self.client.force_login(self.user)

  def get_json(self, url):
    return self.client.get(url, CONTENT_TYPE="application/json").json()

  def test_detail_get_is_nested(self):
    image = self.get_json(f"/systemimages/{self.image.slug}/")
    self.assertEqual(image["osdistro"]["name"], "distro-a")
    self.assertEqual(image["osdistro"]["distType"]["slug"], "rhel")
    # Declared fields keep their shape: the jobserver compares these as IDs.
    self.assertEqual(image["jobservers"], [self.jobserver.id])

  def test_list_stays_flat_after_detail_get(self):
    self.get_json(f"/systemimages/{self.image.slug}/")
    self.assertEqual(self.get_json("/systemimages/")[0]["osdistro"], self.distro.id)
    self.get_json(f"/distros/{self.distro.id}/")
    distros = {d["name"]: d for d in self.get_json("/distros/")}
    self.assertEqual(distros["distro-a"]["distType"], "rhel")
    self.assertFalse(hasattr(SystemImageSerializer.Meta, "depth"))
    self.assertFalse(hasattr(OSDistroAPISerializer.Meta, "depth"))

  def test_patch_relation_after_detail_get(self):
    self.get_json(f"/systemimages/{self.image.slug}/")
    response = self.client.patch(f"/systemimages/{self.image.slug}/",
                                 data=json.dumps({"osdistro": self.other_distro.id}), content_type="application/json")
    self.assertEqual(response.status_code, 200, response.content)
    self.image.refresh_from_db()
    self.assertEqual(self.image.osdistro, self.other_distro)
    # The PATCH reply is the flat object, not the detail one.
    self.assertEqual(response.json()["osdistro"], self.other_distro.id)

  def test_detail_flag_on_list(self):
    images = self.get_json("/systemimages/?detail")
    self.assertEqual(images[0]["osdistro"]["name"], "distro-a")
    distros = {d["name"]: d for d in self.get_json("/distros/?detail")}
    self.assertEqual(distros["distro-a"]["distType"]["slug"], "rhel")

  def test_systems_detail_unchanged(self):
    # SystemAPIView has its own get() and isn't part of this change (#298).
    self.assertEqual(self.get_json(f"/systems/{self.system.id}/")["systemimage"], self.image.slug)


class BMCDetailSerializerTests(TestCase):
  """ /systembmcs/ uses SystemBMCDetailSerializer for details, nested one level.
  Jobserver dns.py and mprov_scripts setupBMC.py read system.hostname,
  network.netmask and the password from ?detail. """

  def setUp(self):
    self.user = User.objects.create(username="bmc-detail-test")
    self.system = System.objects.create(hostname="bmc-detail-node", created_by=self.user)
    self.bmc = SystemBMC.objects.create(system=self.system, ipaddress="10.0.1.5", username="admin", password="bmc-secret")
    self.client.force_login(self.user)

  def get_json(self, url):
    return self.client.get(url, CONTENT_TYPE="application/json").json()

  def test_detail_list(self):
    bmc = self.get_json("/systembmcs/?detail")[0]
    self.assertEqual(bmc["system"]["hostname"], "bmc-detail-node")
    self.assertEqual(bmc["password"], "bmc-secret")
    # Nested one level only.
    self.assertEqual(bmc["system"]["created_by"], self.user.id)

  def test_detail_get_and_list_after_it(self):
    bmc = self.get_json(f"/systembmcs/{self.bmc.id}/")
    self.assertEqual(bmc["system"]["hostname"], "bmc-detail-node")
    self.assertEqual(bmc["password"], "bmc-secret")
    bmc = self.get_json("/systembmcs/")[0]
    self.assertEqual(bmc["system"], self.system.id)
    self.assertNotIn("password", bmc)
