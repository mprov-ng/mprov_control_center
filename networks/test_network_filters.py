import json

from networks.testing import NetworkTestCase


class NetworkAPIViewFilterTests(NetworkTestCase):
  """ GET /networks/ filters by ?isdhcp=, ?managedns= and ?FIELD=. """

  def setUp(self):
    super().setUp()
    self.lan.isdhcp = True
    self.lan.save()

  def slugs(self, url):
    response = self.get_json(url)
    self.assertEqual(response.status_code, 200)
    return [n["slug"] for n in response.json()]

  def test_boolean_filters_in_any_case(self):
    for value in ("True", "true", "1"):
      self.assertEqual(self.slugs(f"/networks/?isdhcp={value}"), ["cluster-lan"])
    self.assertEqual(self.slugs("/networks/?isdhcp=FALSE"), ["mgmt"])

  def test_bad_boolean_is_400(self):
    response = self.get_json("/networks/?managedns=maybe")
    self.assertEqual(response.status_code, 400)
    self.assertIn("managedns", response.json())

  def test_other_field_filters(self):
    self.assertEqual(self.slugs("/networks/?isdhcp=true&name=Mgmt"), [])
    self.assertEqual(self.slugs("/networks/?name=Mgmt"), ["mgmt"])
