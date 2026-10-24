from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase

from systems.models import System, SystemBMC
from systems.views import SystemPowerAPIView


class SystemPowerAPIViewHostnameTests(TestCase):
  """ GET /power/<action>/?hostname= acts only on the exactly-named system. """

  def setUp(self):
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    # "power-node" is a substring of "power-node-2"; a contains lookup made
    # ?hostname=power-node power-cycle both systems (issue #332).
    self.system = System.objects.create(hostname="power-node", created_by=self.user)
    self.bmc = SystemBMC.objects.create(system=self.system, ipaddress="10.0.4.5", username="admin", password="pw")
    self.other = System.objects.create(hostname="power-node-2", created_by=self.user)
    self.other_bmc = SystemBMC.objects.create(system=self.other, ipaddress="10.0.4.6", username="admin", password="pw")
    patcher = mock.patch.object(SystemPowerAPIView, "_doPowerCmd", return_value={"status": 200})
    self.power = patcher.start()
    self.addCleanup(patcher.stop)

  def get_json(self, url):
    return self.client.get(url, CONTENT_TYPE="application/json")

  def test_exact_hostname_only_powers_that_system(self):
    response = self.get_json("/power/status/?hostname=power-node")
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json(), {str(self.bmc): {"status": 200}})
    self.assertEqual(self.power.call_count, 1)
    self.assertEqual(self.power.call_args[0][0], self.bmc)

  def test_partial_hostname_is_404(self):
    # A prefix of a real hostname must not power-cycle the matching hosts.
    response = self.get_json("/power/off/?hostname=power-nod")
    self.assertEqual(response.status_code, 404)
    self.power.assert_not_called()
