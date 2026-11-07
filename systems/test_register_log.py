from django.contrib.auth.models import User
from django.test import TestCase

from networks.models import Network, NetworkType, Switch, SwitchPort
from systems.models import NetworkInterface, System, SystemModel

LOGGER = "mprov.nads"


class SystemRegLogTests(TestCase):
  """ #170: POST /systems/register logs each N.A.D.S. registration, so an
  admin (or an alert on the container log) notices a new node that needs
  configuring. """

  packet = {"vendor": "Dell", "model": "R650", "switch": "sw1", "port": "1/1", "mac": "aa:bb:cc:dd:ee:ff"}

  def register(self, ip="10.0.0.50", **changes):
    return self.client.post("/systems/register", {**self.packet, **changes}, content_type="application/json", REMOTE_ADDR=ip)

  def test_new_mac_is_logged_as_found(self):
    with self.assertLogs(LOGGER, "INFO") as logs:
      self.assertEqual(self.register().status_code, 200)
    self.assertEqual(logs.output, [
      f"INFO:{LOGGER}:nads: aa:bb:cc:dd:ee:ff (10.0.0.50) found on sw1 port 1/1, Dell R650, ready to be assigned"])

  def test_known_unassigned_mac_is_logged_as_seen_again(self):
    self.register()
    with self.assertLogs(LOGGER, "INFO") as logs:
      self.register(switch="sw2", port="2/7")
    self.assertEqual(logs.output, [
      f"INFO:{LOGGER}:nads: aa:bb:cc:dd:ee:ff (10.0.0.50) seen again on sw2 port 2/7, Dell R650, ready to be assigned"])

  def test_null_switch_and_port_show_as_dash(self):
    with self.assertLogs(LOGGER, "INFO") as logs:
      self.register(switch=None, port=None)
    self.assertEqual(logs.output, [
      f"INFO:{LOGGER}:nads: aa:bb:cc:dd:ee:ff (10.0.0.50) found on - port -, Dell R650, ready to be assigned"])

  def test_control_characters_cannot_forge_a_log_line(self):
    with self.assertLogs(LOGGER, "INFO") as logs:
      self.register(model="R650\n[I] nads: forged")
    self.assertEqual(len(logs.records), 1)
    self.assertNotIn("\n", logs.output[0])
    self.assertIn("Dell R650\\n[I] nads: forged, ready", logs.output[0])

  def test_mac_already_on_a_nic_is_not_logged(self):
    user = User.objects.create(username="register-test")
    system = System.objects.create(hostname="c01", created_by=user)
    NetworkInterface.objects.create(system=system, name="eth0", mac=self.packet["mac"])
    with self.assertNoLogs(LOGGER, "INFO"):
      self.assertEqual(self.register().status_code, 200)

  def test_match_to_a_waiting_system_is_logged_as_registered(self):
    user = User.objects.create(username="register-test")
    net_type = NetworkType.objects.create(name="Ethernet")
    net = Network.objects.create(name="Cluster LAN", net_type=net_type, subnet="172.16.0.0", netmask=16)
    switch = Switch.objects.create(hostname="sw1", mgmt_ip="10.0.0.1", mgmt_mac="de:ad:be:ef:00:01", created_by=user)
    port = SwitchPort.objects.create(name="1/1", switch=switch, networks=net)
    model = SystemModel.objects.create(name="R650", vendor="Dell")
    system = System.objects.create(hostname="c01", systemmodel=model, created_by=user)
    NetworkInterface.objects.create(system=system, name="eth0", switch_port=port)
    with self.assertLogs(LOGGER, "INFO") as logs:
      response = self.register()
    self.assertEqual(response.status_code, 200, response.content)
    self.assertEqual(logs.output, [
      f"INFO:{LOGGER}:nads: aa:bb:cc:dd:ee:ff (10.0.0.50) on sw1 port 1/1 registered to c01"])
