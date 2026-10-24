from django.test import TestCase
from django.test.utils import override_settings

from systems.models import NADSSystem

TOKEN = "s3cret-enrollment-token"
PACKET = {"vendor": "Dell", "model": "R650", "switch": "sw1", "port": "1/1",
          "mac": "aa:bb:cc:dd:ee:ff"}


@override_settings(MPROV_ENROLLMENT_TOKEN=TOKEN)
class SystemRegisterEnrollmentTokenTests(TestCase):
  """ POST /systems/register is gated behind the deployment enrollment
      token (X-MProv-Enrollment-Token header), issue #318.  The token is
      opt-in: with no token configured registration stays open, with a
      warning logged. """

  def register(self, **changes):
    return self.client.post("/systems/register", {**PACKET, **changes},
                            content_type="application/json")

  def test_no_token_header_is_rejected_and_stores_nothing(self):
    response = self.register()
    self.assertEqual(response.status_code, 403)
    self.assertEqual(NADSSystem.objects.count(), 0)

  def test_wrong_token_is_rejected_and_stores_nothing(self):
    response = self.client.post("/systems/register", PACKET,
                                content_type="application/json",
                                HTTP_X_MPROV_ENROLLMENT_TOKEN="wrong-token")
    self.assertEqual(response.status_code, 403)
    self.assertEqual(NADSSystem.objects.count(), 0)

  def test_correct_token_registers_the_mac(self):
    response = self.client.post("/systems/register", PACKET,
                                content_type="application/json",
                                HTTP_X_MPROV_ENROLLMENT_TOKEN=TOKEN)
    self.assertEqual(response.status_code, 200)
    self.assertTrue(NADSSystem.objects.filter(mac=PACKET["mac"]).exists())

  @override_settings(MPROV_ENROLLMENT_TOKEN="")
  def test_open_registration_logs_warning_when_no_token_configured(self):
    with self.assertLogs("systems.views", level="WARNING") as logs:
      response = self.register()
    self.assertEqual(response.status_code, 200)
    self.assertTrue(NADSSystem.objects.filter(mac=PACKET["mac"]).exists())
    self.assertIn("MPROV_ENROLLMENT_TOKEN", "\n".join(logs.output))
