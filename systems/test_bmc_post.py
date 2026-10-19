from django.contrib.auth.models import User
from django.test import TestCase

from systems.models import System, SystemBMC


class SystemBMCPasswordTests(TestCase):
  """ The BMC password is write-only, except for a single entry or ?detail, which
  mprov_scripts' setupBMC.py reads. """

  def setUp(self):
    self.user = User.objects.create(username="bmc-test")
    self.system = System.objects.create(hostname="bmc-node", created_by=self.user)
    self.bmc = SystemBMC.objects.create(system=self.system, ipaddress="10.0.1.5", username="admin", password="bmc-secret")
    self.client.force_login(self.user)

  def get_json(self, url):
    return self.client.get(url, CONTENT_TYPE="application/json")

  def test_post_without_password(self):
    other = System.objects.create(hostname="bmc-node2", created_by=self.user)
    response = self.client.post("/systembmcs/", data=f'{{"system": {other.id}, "ipaddress": "10.0.1.7"}}',
                                content_type="application/json")
    self.assertEqual(response.status_code, 201, response.content)
    self.assertEqual(SystemBMC.objects.get(system=other).ipaddress, "10.0.1.7")
