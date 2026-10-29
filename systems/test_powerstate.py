from common.testing import APITestCase
from systems.models import System


class PowerstateTests(APITestCase):
  """ GET /systems/<pk>/?powerstate redirects to a power state image, the unknown one when it can't tell. """

  def powerstate(self, pk):
    response = self.client.get(f"/systems/{pk}/?powerstate")
    self.assertEqual(response.status_code, 302)
    return response["Location"]

  def test_unknown_system(self):
    # issue #324: an unknown or non-numeric id was a 500.
    for pk in ("999", "abc"):
      self.assertEqual(self.powerstate(pk), "/static/images/power_unknown.svg", pk)

  def test_system_without_bmc(self):
    system = System.objects.create(hostname="node01", created_by=self.user)
    self.assertEqual(self.powerstate(system.pk), "/static/images/power_unknown.svg")
