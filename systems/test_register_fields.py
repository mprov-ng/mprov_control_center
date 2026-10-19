from django.test import TestCase


class SystemRegAPIViewTests(TestCase):
  """ POST /systems/register records unknown MACs as N.A.D.S. systems. """

  packet = {"vendor": "Dell", "model": "R650", "switch": "sw1", "port": "1/1", "mac": "aa:bb:cc:dd:ee:ff"}

  def register(self, **changes):
    return self.client.post("/systems/register", {**self.packet, **changes}, content_type="application/json")

  def test_missing_field_is_400(self):
    packet = dict(self.packet)
    del packet["vendor"]
    del packet["mac"]
    response = self.client.post("/systems/register", packet, content_type="application/json")
    self.assertEqual(response.status_code, 400)
    self.assertEqual(set(response.json()), {"vendor", "mac"})
