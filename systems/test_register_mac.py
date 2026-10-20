from django.contrib.auth.models import User
from django.test import TestCase

from networks.models import Switch


class SystemRegAPIViewTests(TestCase):
  """ POST /systems/register records unknown MACs as N.A.D.S. systems. """

  packet = {"vendor": "Dell", "model": "R650", "switch": "sw1", "port": "1/1", "mac": "aa:bb:cc:dd:ee:ff"}

  def register(self, **changes):
    return self.client.post("/systems/register", {**self.packet, **changes}, content_type="application/json")

  def test_known_mac_on_a_new_port_updates_the_entry(self):
    from systems.models import NADSSystem
    self.assertEqual(self.register().status_code, 200)
    self.assertEqual(self.register(switch="sw2", port="2/7").status_code, 200)
    nads = NADSSystem.objects.get(mac=self.packet["mac"])
    self.assertEqual((nads.switch, nads.port), ("sw2", "2/7"))
    self.assertEqual(NADSSystem.objects.count(), 1)

  def test_switch_hostname_shared_by_two_switches_still_registers(self):
    from systems.models import NADSSystem
    user = User.objects.create(username="register-test")
    for mac in ("de:ad:be:ef:00:01", "de:ad:be:ef:00:02"):
      Switch.objects.create(hostname="sw1", mgmt_ip="10.0.0.1", mgmt_mac=mac, created_by=user)
    self.assertEqual(self.register().status_code, 200)
    self.assertTrue(NADSSystem.objects.filter(mac=self.packet["mac"]).exists())
