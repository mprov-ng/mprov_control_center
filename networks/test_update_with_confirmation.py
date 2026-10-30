import json

from networks.testing import NetworkTestCase


class NetworkUpdateWithConfirmationAPITests(NetworkTestCase):
  """ POST /networks/<pk>/update-with-confirmation/ asks before a subnet change. """

  def post(self, body):
    return self.client.post(f"/networks/{self.lan.pk}/update-with-confirmation/", body, content_type="application/json")

  def test_same_netmask_as_a_string_is_not_a_change(self):
    response = self.post(json.dumps({"network_data": {"netmask": "16", "domain": "cluster"}}))
    self.assertEqual(response.status_code, 200)
    self.assertNotIn("requires_confirmation", response.json())
    self.lan.refresh_from_db()
    self.assertEqual(self.lan.domain, "cluster")

  def test_subnet_change_asks_first(self):
    response = self.post(json.dumps({"network_data": {"subnet": "172.17.0.0"}}))
    self.assertEqual(response.status_code, 200)
    self.assertTrue(response.json()["requires_confirmation"])
    self.lan.refresh_from_db()
    self.assertEqual(self.lan.subnet, "172.16.0.0")

  def test_non_object_body_is_400(self):
    for body in ("[]", '"x"', json.dumps({"network_data": []})):
      self.assertEqual(self.post(body).status_code, 400, body)
