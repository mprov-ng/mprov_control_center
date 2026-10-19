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

  def test_by_id(self):
    response = self.get_json(f"/power/status/?id={self.system.id}")
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json(), {str(self.bmc): {"status": 200}})

  def test_unknown_id_is_404(self):
    self.assertEqual(self.get_json("/power/status/?id=999").status_code, 404)
    self.power.assert_not_called()

  def test_bad_id_is_400(self):
    self.assertEqual(self.get_json("/power/status/?id=abc").status_code, 400)
