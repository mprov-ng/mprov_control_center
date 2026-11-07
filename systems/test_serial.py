import json

from django.contrib.admin.sites import site
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from networks.models import Network, NetworkType, Switch, SwitchPort
from systems.models import NADSSystem, NetworkInterface, System, SystemModel, SystemSerialHistory, clean_serial
from systems.test_provision import ProvisionTestCase

LOGGER = "mprov.serial"


def history(system):
  return list(SystemSerialHistory.objects.filter(system=system).values_list("old_serial", "new_serial", "source"))


class CleanSerialTests(TestCase):
  """ #60: dmidecode's placeholders for "no serial number" are ignored. """

  def test_placeholders_are_none(self):
    for value in (None, "", "  ", "To Be Filled By O.E.M.", "Not Specified", "n/a", "N/A", "Default string",
                  "System Serial Number", "0", "None"):
      self.assertIsNone(clean_serial(value), value)

  def test_a_real_serial_is_stripped(self):
    self.assertEqual(clean_serial("  ABC123\n"), "ABC123")


class SetSerialTests(TestCase):
  """ #60: System.set_serial(), for serials reported by a node or N.A.D.S. """

  def setUp(self):
    self.user = User.objects.create(username="serial-test")
    self.system = System.objects.create(hostname="c01", created_by=self.user)

  def test_change_is_saved_logged_and_kept_in_history(self):
    with self.assertLogs(LOGGER, "INFO") as logs:
      self.assertTrue(self.system.set_serial("ABC123", "node"))
    self.assertEqual(System.objects.get(pk=self.system.pk).serial, "ABC123")
    self.assertEqual(logs.output, [f"INFO:{LOGGER}:serial: c01 changed - -> ABC123 (node)"])
    with self.assertLogs(LOGGER, "INFO") as logs:
      self.assertTrue(self.system.set_serial("XYZ789", "node"))
    self.assertEqual(logs.output, [f"INFO:{LOGGER}:serial: c01 changed ABC123 -> XYZ789 (node)"])
    self.assertEqual(history(self.system), [("ABC123", "XYZ789", "node"), (None, "ABC123", "node")])

  def test_same_serial_is_a_no_op(self):
    self.system.set_serial("ABC123", "node")
    with self.assertNoLogs(LOGGER, "INFO"):
      self.assertFalse(self.system.set_serial(" ABC123 ", "node"))
    self.assertEqual(len(history(self.system)), 1)

  def test_placeholder_never_wipes_a_serial(self):
    self.system.set_serial("ABC123", "node")
    self.assertFalse(self.system.set_serial("To Be Filled By O.E.M.", "node"))
    self.assertFalse(self.system.set_serial(None, "nads"))
    self.assertEqual(System.objects.get(pk=self.system.pk).serial, "ABC123")

  def test_set_serial_does_not_fire_system_save(self):
    # a node reporting its serial shouldn't touch "updated" or queue jobs.
    updated = System.objects.get(pk=self.system.pk).updated
    self.system.set_serial("ABC123", "node")
    self.assertEqual(System.objects.get(pk=self.system.pk).updated, updated)


class SelfSerialTests(ProvisionTestCase):
  """ #60: POST /systems/?self {"serial": ...} from report_booted.py. """

  def setUp(self):
    super().setUp()
    self.client.force_login(self.user)
    NetworkInterface.objects.create(system=self.system, name="eth0", ipaddress="10.0.0.20", bootable=True)

  def post_self(self, body):
    return self.client.post("/systems/?self", json.dumps(body), content_type="application/json", REMOTE_ADDR="10.0.0.20")

  def serial(self):
    return System.objects.get(pk=self.system.pk).serial

  def test_serial_is_saved(self):
    response = self.post_self({"serial": "ABC123"})
    self.assertEqual(response.status_code, 200, response.content)
    self.assertEqual(response.json(), {"provision": True, "bootable_nic": "eth0"})
    self.assertEqual(self.serial(), "ABC123")
    self.assertEqual(history(self.system), [(None, "ABC123", "node")])

  def test_placeholder_is_accepted_and_ignored(self):
    self.assertEqual(self.post_self({"serial": "To Be Filled By O.E.M."}).status_code, 200)
    self.assertIsNone(self.serial())
    self.assertEqual(history(self.system), [])

  def test_invalid_serial_is_400_and_changes_nothing(self):
    for bad in (123, None, ["ABC"], "x" * 256):
      response = self.post_self({"serial": bad, "booted": True})
      self.assertEqual(response.status_code, 400, bad)
      self.assertIn("serial", response.json())
    system = System.objects.get(pk=self.system.pk)
    self.assertIsNone(system.serial)
    self.assertIsNone(system.last_booted)

  def test_serial_with_booted(self):
    self.assertEqual(self.post_self({"booted": True, "serial": "ABC123"}).status_code, 200)
    system = System.objects.get(pk=self.system.pk)
    self.assertEqual(system.serial, "ABC123")
    self.assertIsNotNone(system.last_booted)


class ApiAndAdminSerialTests(TestCase):
  """ #60: serials set by hand, in the admin or through /systems/, are kept
  in the history with who set them. """

  def setUp(self):
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    self.system = System.objects.create(hostname="c01", created_by=self.user)

  def test_api_patch_is_recorded(self):
    response = self.client.patch(f"/systems/{self.system.pk}/", json.dumps({"serial": "ABC123"}), content_type="application/json")
    self.assertEqual(response.status_code, 200, response.content)
    self.assertEqual(response.json()["serial"], "ABC123")
    entry = SystemSerialHistory.objects.get(system=self.system)
    self.assertEqual((entry.old_serial, entry.new_serial, entry.source, entry.changed_by), (None, "ABC123", "api", self.user))

  def test_api_patch_of_another_field_is_not_recorded(self):
    response = self.client.patch(f"/systems/{self.system.pk}/", json.dumps({"stateful": True}), content_type="application/json")
    self.assertEqual(response.status_code, 200, response.content)
    self.assertEqual(history(self.system), [])

  def test_serial_is_in_the_list(self):
    self.system.set_serial("ABC123", "node")
    response = self.client.get("/systems/", CONTENT_TYPE="application/json")
    self.assertEqual(response.json()[0]["serial"], "ABC123")

  def test_admin_edit_is_recorded(self):
    request = RequestFactory().post("/")
    request.user = self.user
    admin = site._registry[System]
    system = System.objects.get(pk=self.system.pk)
    system.serial = "XYZ789"
    admin.save_model(request, system, form=None, change=True)
    entry = SystemSerialHistory.objects.get(system=self.system)
    self.assertEqual((entry.old_serial, entry.new_serial, entry.source, entry.changed_by), (None, "XYZ789", "admin", self.user))

  def test_admin_change_page_shows_serial_and_history(self):
    self.system.set_serial("ABC123", "node")
    response = self.client.get(f"/admin/systems/system/{self.system.pk}/change/")
    self.assertEqual(response.status_code, 200)
    self.assertContains(response, 'name="serial"')
    self.assertContains(response, "Serial Number History")

  def test_admin_search_by_serial(self):
    self.system.set_serial("ABC123", "node")
    System.objects.create(hostname="c02", created_by=self.user)
    response = self.client.get("/admin/systems/system/?q=ABC123")
    self.assertContains(response, "c01")
    self.assertNotContains(response, ">c02<")


class NadsSerialTests(TestCase):
  """ #60: the serial in a N.A.D.S. packet is kept on the N.A.D.S. system,
  and carried to the system it registers to or is assigned to. """

  packet = {"vendor": "Dell", "model": "R650", "switch": "sw1", "port": "1/1", "mac": "aa:bb:cc:dd:ee:ff", "serial": "ABC123"}

  def setUp(self):
    self.user = User.objects.create(username="register-test")

  def register(self, **changes):
    return self.client.post("/systems/register", {**self.packet, **changes}, content_type="application/json")

  def test_unmatched_packet_keeps_serial_on_nads_system(self):
    with self.assertLogs("mprov.nads", "INFO") as logs:
      self.assertEqual(self.register().status_code, 200)
    self.assertEqual(NADSSystem.objects.get(mac=self.packet["mac"]).serial, "ABC123")
    self.assertIn("Dell R650, serial ABC123, ready to be assigned", logs.output[0])

  def test_placeholder_or_missing_serial_is_none(self):
    self.register(serial="To Be Filled By O.E.M.")
    self.assertIsNone(NADSSystem.objects.get(mac=self.packet["mac"]).serial)
    packet = dict(self.packet)
    del packet["serial"]
    self.assertEqual(self.client.post("/systems/register", packet, content_type="application/json").status_code, 200)

  def test_match_copies_serial_to_system(self):
    net_type = NetworkType.objects.create(name="Ethernet")
    net = Network.objects.create(name="Cluster LAN", net_type=net_type, subnet="172.16.0.0", netmask=16)
    switch = Switch.objects.create(hostname="sw1", mgmt_ip="10.0.0.1", mgmt_mac="de:ad:be:ef:00:01", created_by=self.user)
    port = SwitchPort.objects.create(name="1/1", switch=switch, networks=net)
    model = SystemModel.objects.create(name="R650", vendor="Dell")
    system = System.objects.create(hostname="c01", systemmodel=model, created_by=self.user)
    NetworkInterface.objects.create(system=system, name="eth0", switch_port=port)
    self.assertEqual(self.register().status_code, 200)
    self.assertEqual(System.objects.get(pk=system.pk).serial, "ABC123")
    self.assertEqual(history(system), [(None, "ABC123", "nads")])

  def test_assigning_a_nads_system_copies_serial(self):
    system = System.objects.create(hostname="c01", created_by=self.user)
    NetworkInterface.objects.create(system=system, name="eth0", bootable=True)
    self.register()
    nads = NADSSystem.objects.get(mac=self.packet["mac"])
    nads.system = system
    nads.save()
    system = System.objects.get(pk=system.pk)
    self.assertEqual(system.serial, "ABC123")
    self.assertEqual(NetworkInterface.objects.get(system=system).mac, self.packet["mac"])
    self.assertEqual(history(system), [(None, "ABC123", "nads")])
