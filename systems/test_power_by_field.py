from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase

from systems.models import System, SystemBMC
from systems.views import SystemPowerAPIView


class SystemPowerAPIViewQueryTests(TestCase):
  """ GET /power/<action>/ finds the BMCs to act on from the query string. """

  def setUp(self):
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    self.system = System.objects.create(hostname="power-node", created_by=self.user)
    self.bmc = SystemBMC.objects.create(system=self.system, ipaddress="10.0.2.5", username="admin", password="pw")
    patcher = mock.patch.object(SystemPowerAPIView, "_doPowerCmd", return_value={"status": 200})
    self.power = patcher.start()
    self.addCleanup(patcher.stop)

  def get_json(self, url):
    return self.client.get(url, CONTENT_TYPE="application/json")

  def test_by_bmc_field(self):
    response = self.get_json("/power/status/?ipaddress=10.0.2.5")
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json(), {str(self.bmc): {"status": 200}})

  def test_field_filter_acts_on_at_most_10(self):
    for i in range(12):
      system = System.objects.create(hostname=f"many{i}", created_by=self.user)
      SystemBMC.objects.create(system=system, ipaddress=f"10.0.3.{i}", username="ops", password="pw")
    response = self.get_json("/power/off/?username=ops")
    self.assertEqual(response.status_code, 200)
    self.assertEqual(self.power.call_count, 10)

  def test_no_filter_is_400(self):
    self.assertEqual(self.get_json("/power/off/").status_code, 400)
    self.power.assert_not_called()

  def test_unknown_field_is_400(self):
    self.assertEqual(self.get_json("/power/off/?nope=1").status_code, 400)

  def test_no_match_is_404(self):
    self.assertEqual(self.get_json("/power/off/?ipaddress=10.9.9.9").status_code, 404)
    self.power.assert_not_called()
