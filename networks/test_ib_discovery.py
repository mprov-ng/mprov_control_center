""" #566: switches without a management IP or MAC, InfiniBand GUIDs, unique
switch hostnames, and nodes adding their own NICs, switches and ports. """
import json

from django.contrib.auth.models import Permission, User
from django.test import override_settings

from authcustom.models import UserToken
from common.testing import APITestCase
from mprov_control_center.version import API_VERSION
from networks.models import Switch, SwitchPort
from pki.test_auth import DENIED, AgentTestCase
from systems.models import NetworkInterface, SystemBMC

GUID = "0x506b4b0300abcdef"


class SwitchAndGuidTests(APITestCase):
  """ The model and API, as a person. """

  def post(self, url, body):
    return self.client.post(url, json.dumps(body), content_type="application/json")

  def test_a_switch_needs_no_management_ip_or_mac(self):
    response = self.post("/switches/", {"hostname": "ib-sw1"})
    self.assertEqual(response.status_code, 201, response.content)
    switch = Switch.objects.get(hostname="ib-sw1")
    self.assertEqual((switch.mgmt_ip, switch.mgmt_mac, switch.guid), (None, None, None))
    # an empty MAC is stored as NULL too
    self.post("/switches/", {"hostname": "ib-sw2", "mgmt_mac": "", "guid": ""})
    self.assertEqual(Switch.objects.filter(mgmt_mac=None, guid=None).count(), 2)

  def test_guid_is_lowercase_unique_and_checked(self):
    self.assertEqual(self.post("/switches/", {"hostname": "a", "guid": GUID.upper().replace("0X", "0x")})
                     .status_code, 201)
    self.assertEqual(Switch.objects.get(hostname="a").guid, GUID)
    response = self.post("/switches/", {"hostname": "b", "guid": GUID.upper()})
    self.assertEqual(response.status_code, 400)
    self.assertIn("guid", response.json())
    response = self.post("/switches/", {"hostname": "c", "guid": "0x1234"})
    self.assertEqual(response.status_code, 400)
    self.assertIn("16 hex digits", response.json()["guid"][0])
    self.assertEqual(self.get_json(f"/switches/?guid={GUID}").json()[0]["hostname"], "a")

  def test_switch_hostnames_are_unique(self):
    self.post("/switches/", {"hostname": "sw1"})
    response = self.post("/switches/", {"hostname": "sw1"})
    self.assertEqual(response.status_code, 400)
    self.assertEqual(response.json(), {"hostname": ["Switch with this Host Name already exists."]})

  def test_nic_guid(self):
    from systems.models import System
    system = System.objects.create(hostname="c01", created_by=self.user)
    response = self.post("/networkinterfaces/", {"system": system.pk, "name": "ib0", "guid": "0x" + GUID[2:].upper()})
    self.assertEqual(response.status_code, 201, response.content)
    self.assertEqual(NetworkInterface.objects.get(name="ib0").guid, GUID)
    self.assertEqual(self.post("/networkinterfaces/", {"system": system.pk, "name": "ib1", "guid": GUID})
                     .status_code, 400)
    # a person isn't held to the node checks below
    SystemBMC.objects.create(system=System.objects.create(hostname="c02", created_by=self.user),
                             ipaddress="10.0.1.2", mac="aa:bb:cc:dd:ee:01")
    self.assertEqual(self.post("/networkinterfaces/", {"system": system.pk, "name": "eth0",
                                                       "mac": "aa:bb:cc:dd:ee:01"}).status_code, 201)

  def test_admin_forms(self):
    response = self.client.post("/admin/networks/switch/add/", {
      "hostname": "sw-admin", "mgmt_ip": "", "mgmt_mac": "", "guid": GUID.upper().replace("0X", "0x"),
      "timestamp_0": "2026-01-01", "timestamp_1": "00:00:00", "updated_0": "2026-01-01", "updated_1": "00:00:00",
      "switchport_set-TOTAL_FORMS": "0", "switchport_set-INITIAL_FORMS": "0"})
    self.assertEqual(response.status_code, 302, response.content[:2000])
    switch = Switch.objects.get(hostname="sw-admin")
    self.assertEqual((switch.mgmt_ip, switch.mgmt_mac, switch.guid), (None, None, GUID))
    self.assertContains(self.client.get("/admin/networks/switch/"), GUID)


class NodeDiscoveryRuleTests(AgentTestCase):
  """ What a node's certificate may add and change for itself. """

  def setUp(self):
    super().setUp()
    self.lan_switch = Switch.objects.create(hostname="lan-sw", created_by=self.admin, network=self.lan)
    self.lan_port = SwitchPort.objects.create(name="1", switch=self.lan_switch, networks=self.lan)
    self.other_port = SwitchPort.objects.create(name="2", switch=self.lan_switch, networks=self.other_net)
    self.plain_port = SwitchPort.objects.create(name="3", switch=self.lan_switch)

  def assertStatus(self, status, method, url, body=None):
    response = self.as_c01(method, url, body)
    self.assertEqual(response.status_code, status, f"{method} {url}: {response.content[:300]}")
    return response

  def test_adds_its_own_nics(self):
    # an InfiniBand interface: a GUID and no MAC (IPoIB MACs change every boot)
    self.assertStatus(201, "POST", "/networkinterfaces/", {"system": self.c01.pk, "name": "ib0", "mtu": 2044,
                                                            "guid": GUID.upper().replace("0X", "0x")})
    nic = NetworkInterface.objects.get(name="ib0")
    self.assertEqual((nic.system, nic.mac, nic.guid, nic.mtu), (self.c01, None, GUID, 2044))
    self.assertStatus(201, "POST", "/networkinterfaces/", {"system": self.c01.pk, "name": "eth1",
                                                            "mac": "52:54:00:00:00:01"})

  def test_not_for_another_system_or_with_other_fields(self):
    self.assertStatus(403, "POST", "/networkinterfaces/", {"system": self.c02.pk, "name": "eth9"})
    self.assertStatus(403, "POST", "/networkinterfaces/", {"name": "eth9"})
    self.assertStatus(403, "POST", "/networkinterfaces/", {"system": self.c01.pk, "name": "eth9",
                                                            "ipaddress": "10.0.0.99"})
    response = self.assertStatus(403, "POST", "/networkinterfaces/", {"system": self.c01.pk, "name": "eth9",
                                                                       "network": self.other_net.pk})
    self.assertEqual(response.json()["detail"], f"{self.c01_cred.user.username} may not POST this.")
    self.assertStatus(403, "DELETE", f"/networkinterfaces/{self.nic1.pk}/")

  def test_no_mac_another_system_has(self):
    NetworkInterface.objects.filter(pk=self.nic2.pk).update(mac="aa:bb:cc:dd:ee:01")
    SystemBMC.objects.filter(pk=self.bmc2.pk).update(mac="aa:bb:cc:dd:ee:02")
    for mac in ("AA:BB:CC:DD:EE:01", "aa:bb:cc:dd:ee:02"):
      response = self.assertStatus(400, "POST", "/networkinterfaces/", {"system": self.c01.pk, "name": "eth9",
                                                                         "mac": mac})
      self.assertEqual(response.json(), {"mac": ["Another system already has this MAC address."]})
    # its own MAC (e.g. its BMC's, or a re-run) is fine
    SystemBMC.objects.filter(pk=self.bmc1.pk).update(mac="aa:bb:cc:dd:ee:03")
    self.assertStatus(201, "POST", "/networkinterfaces/", {"system": self.c01.pk, "name": "eth9",
                                                            "mac": "aa:bb:cc:dd:ee:03"})
    self.assertFalse(NetworkInterface.objects.filter(name="eth9", system=self.c02).exists())

  def test_changes_its_own_nics(self):
    url = f"/networkinterfaces/{self.nic1.pk}/"
    self.assertStatus(200, "PATCH", url, {"id": self.nic1.pk, "name": "eno1", "mtu": 9000, "guid": GUID})
    self.assertStatus(200, "PATCH", url, {"switch_port": self.lan_port.pk})    # the NIC's network
    self.assertStatus(200, "PATCH", url, {"switch_port": self.plain_port.pk})  # no network
    response = self.assertStatus(400, "PATCH", url, {"switch_port": self.other_port.pk})
    self.assertEqual(response.json(), {"switch_port": ["This switch port is on a different network from this interface."]})
    nic = NetworkInterface.objects.get(pk=self.nic1.pk)
    self.assertEqual((nic.name, nic.mtu, nic.guid, nic.switch_port), ("eno1", 9000, GUID, self.plain_port))
    self.assertStatus(403, "PATCH", url, {"network": self.other_net.pk})
    self.assertStatus(403, "PATCH", f"/networkinterfaces/{self.nic2.pk}/", {"name": "x"})

  def test_switches_and_ports(self):
    self.assertStatus(200, "GET", "/switches/?hostname=lan-sw")
    self.assertStatus(200, "GET", f"/switches/{self.lan_switch.pk}/")
    self.assertStatus(404, "GET", f"/switches/?guid={GUID}")
    response = self.assertStatus(201, "POST", "/switches/", {"hostname": "ib-sw1", "guid": GUID})
    switch = Switch.objects.get(pk=response.json()["id"])
    self.assertEqual((switch.mgmt_ip, switch.mgmt_mac, switch.created_by), (None, None, self.c01_cred.user))
    self.assertStatus(200, "GET", f"/switches/?guid={GUID}")
    # a boot race: the second node gets a 400 and looks it up instead
    self.assertEqual(self.assertStatus(400, "POST", "/switches/", {"hostname": "ib-sw1"}).json(),
                     {"hostname": ["Switch with this Host Name already exists."]})
    # management details are for people to enter: the job servers serve them in DHCP and DNS
    self.assertStatus(403, "POST", "/switches/", {"hostname": "x", "mgmt_ip": "10.0.0.1"})
    self.assertStatus(403, "POST", "/switches/", {"hostname": "x", "mgmt_mac": "aa:bb:cc:dd:ee:ff"})
    self.assertStatus(403, "POST", "/switches/", {"hostname": "x", "network": self.lan.pk})
    self.assertStatus(403, "PATCH", f"/switches/{switch.pk}/", {"guid": None})
    self.assertStatus(403, "DELETE", f"/switches/{switch.pk}/")
    self.assertStatus(403, "GET", f"/switches/?network={self.lan.slug}")

    self.assertStatus(201, "POST", "/switchports/", {"name": "1", "switch": switch.pk})
    port = SwitchPort.objects.get(switch=switch)
    self.assertStatus(200, "GET", f"/switchports/?switch={switch.pk}&name=1")
    self.assertStatus(200, "GET", f"/switchports/{port.pk}/")
    self.assertStatus(403, "POST", "/switchports/", {"name": "2", "switch": switch.pk, "networks": self.lan.pk})
    self.assertStatus(403, "PATCH", f"/switchports/{port.pk}/", {"name": "9"})
    self.assertStatus(403, "DELETE", f"/switchports/{port.pk}/")

  def test_job_servers_unchanged(self):
    response = self.as_js("POST", "/switches/", {"hostname": "js-sw"})
    self.assertIn(response.status_code, DENIED)
    response = self.as_js("POST", "/networkinterfaces/", {"system": self.c01.pk, "name": "x"})
    self.assertIn(response.status_code, DENIED)


@override_settings(MPROV_SKIP_VERSION_CHECK=False)
class TokenWithoutCertificateTests(APITestCase):
  """ mprov_jobserver#15 uses a staff user's API token, no certificate: Django
  model permissions apply, not the node rules. """

  def setUp(self):
    super().setUp()
    self.client.logout()
    self.staff = User.objects.create_user("fabric", "f@example.com", "pw", is_staff=True)
    _, self.secret = UserToken.make(self.staff, "ib")

  def post(self, body):
    return self.client.post("/switches/", json.dumps(body), content_type="application/json",
                            HTTP_AUTHORIZATION=f"Token {self.secret}", HTTP_MPROV_VERSION=API_VERSION)

  def test_model_permissions(self):
    response = self.post({"hostname": "ib-sw1", "guid": GUID})
    self.assertEqual(response.status_code, 403)
    self.assertIn("networks.add_switch", response.json()["detail"])
    self.staff.user_permissions.add(Permission.objects.get(codename="add_switch"))
    response = self.post({"hostname": "ib-sw1", "guid": GUID, "mgmt_ip": "10.0.5.1"})
    self.assertEqual(response.status_code, 201, response.content)
    self.assertEqual(Switch.objects.get(hostname="ib-sw1").created_by, self.staff)


class HostnameMigrationCheckTests(APITestCase):
  """ The migration that makes Switch.hostname unique stops first, naming
  switches that share a hostname. """

  def check(self):
    import importlib
    from django.apps import apps
    module = importlib.import_module("networks.migrations.0022_switch_guid_unique_hostname")
    module.check_unique_hostnames(apps, None)

  def test_names_the_duplicates(self):
    from django.db import connection
    Switch.objects.create(hostname="sw1", created_by=self.user)
    self.check()  # no duplicates: carries on
    if connection.vendor != "sqlite":
      self.skipTest("only SQLite's unique index allows hostnames that differ in case")
    other = Switch.objects.create(hostname="SW1", created_by=self.user)
    with self.assertRaises(RuntimeError) as raised:
      self.check()
    self.assertIn(f"sw1: switch ids {Switch.objects.get(hostname='sw1').pk}, {other.pk}", str(raised.exception))
