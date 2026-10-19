from django.test import TestCase


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
