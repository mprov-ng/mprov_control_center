import json

from networks.models import Switch
from networks.testing import NetworkTestCase


class SwitchCreateTests(NetworkTestCase):
  """ POST /switches/ doesn't need a network or created_by. """

  def test_create_without_network(self):
    response = self.client.post("/switches/", json.dumps({"hostname": "sw9", "mgmt_ip": "10.0.0.9", "mgmt_mac": "de:ad:be:ef:00:09"}),
                                content_type="application/json")
    self.assertEqual(response.status_code, 201, response.content)
    switch = Switch.objects.get(hostname="sw9")
    self.assertIsNone(switch.network)
    self.assertEqual(switch.created_by, self.user)
