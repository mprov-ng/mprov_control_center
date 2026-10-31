from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from systems.models import NetworkInterface, System, SystemBMC


class BMCPasswordOwnSystemTests(TestCase):
  """ Only the system itself gets its BMC password (#316): /systembmcs/<pk>/,
  ?system=ID&detail (how mprov_scripts' setupBMC.py reads it) or ?self, from
  one of the system's network interface addresses. """

  def setUp(self):
    self.user = User.objects.create(username="bmc-own-test")
    self.node = System.objects.create(hostname="node01", created_by=self.user)
    self.other = System.objects.create(hostname="node02", created_by=self.user)
    NetworkInterface.objects.create(system=self.node, name="ens18", ipaddress="10.0.0.11")
    NetworkInterface.objects.create(system=self.node, name="ens19", ipaddress="10.9.0.11")
    NetworkInterface.objects.create(system=self.other, name="ens18", ipaddress="10.0.0.12")
    self.bmc = SystemBMC.objects.create(system=self.node, ipaddress="10.1.0.11", username="admin", password="node01-secret")
    SystemBMC.objects.create(system=self.other, ipaddress="10.1.0.12", username="admin", password="node02-secret")
    self.client.force_login(self.user)

  def get(self, url, client="10.0.0.11", **extra):
    return self.client.get(url, CONTENT_TYPE="application/json", REMOTE_ADDR=client, **extra)

  def reads(self):
    return (f"/systembmcs/{self.bmc.pk}/", f"/systembmcs/?system={self.node.pk}&detail")

  def password(self, response):
    self.assertEqual(response.status_code, 200, response.content)
    body = response.json()
    return (body[0] if isinstance(body, list) else body).get("password")

  def test_the_system_itself_gets_it(self):
    for url in self.reads():
      for client in ("10.0.0.11", "10.9.0.11"):
        with self.subTest(url=url, client=client):
          self.assertEqual(self.password(self.get(url, client=client)), "node01-secret")

  def test_anyone_else_doesnt(self):
    # another system, an address no system has, and the test client's own.
    for url in self.reads():
      for client in ("10.0.0.12", "192.0.2.1", "127.0.0.1"):
        with self.subTest(url=url, client=client):
          self.assertIsNone(self.password(self.get(url, client=client)))

  def test_unscoped_detail_never_does(self):
    response = self.get("/systembmcs/?detail", client="10.0.0.11")
    self.assertEqual([b.get("password") for b in response.json()], [None, None])

  def test_self(self):
    response = self.get("/systembmcs/?self", client="10.9.0.11")
    self.assertEqual(response.status_code, 200)
    rows = response.json()
    self.assertEqual([(r["system"]["hostname"], r["password"]) for r in rows], [("node01", "node01-secret")])

  def test_self_from_an_unknown_address_is_404(self):
    response = self.get("/systembmcs/?self", client="192.0.2.1")
    self.assertEqual(response.status_code, 404)
    self.assertIn("192.0.2.1", response.json()["detail"])

  def test_self_with_another_systems_filter_finds_nothing(self):
    self.assertEqual(self.get(f"/systembmcs/?self&system={self.other.pk}").status_code, 404)

  def test_a_forged_forwarded_header_is_ignored(self):
    response = self.get("/systembmcs/?self", client="192.0.2.1", HTTP_X_FORWARDED_FOR="10.0.0.11")
    self.assertEqual(response.status_code, 404)

  @override_settings(TRUSTED_PROXIES=["192.0.2.1"])
  def test_a_trusted_proxys_forwarded_header_is_used(self):
    response = self.get(f"/systembmcs/?system={self.node.pk}&detail", client="192.0.2.1", HTTP_X_FORWARDED_FOR="10.0.0.11")
    self.assertEqual(self.password(response), "node01-secret")

  def test_a_bad_system_id_has_no_password(self):
    self.assertEqual(self.get("/systembmcs/?system=abc&detail").status_code, 400)

  def test_writes_never_return_it(self):
    response = self.client.patch(f"/systembmcs/{self.bmc.pk}/", data='{"username": "root"}',
                                 content_type="application/json", REMOTE_ADDR="10.0.0.11")
    self.assertEqual(response.status_code, 200, response.content)
    self.assertNotIn("password", response.json())
