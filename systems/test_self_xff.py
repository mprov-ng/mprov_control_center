import json

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from systems.models import NetworkInterface, System


@override_settings(TRUSTED_PROXIES=[])
class SelfForgedXFFTests(TestCase):
  """ GET and POST /systems/?self identify the caller by its socket peer
  (get_client_ip), like /images/ and /ipxe/.  A forged X-Forwarded-For must
  not let one node read or change another node's record (#320). """

  def setUp(self):
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    self.victim = self.make_system("victim", "10.0.0.8")
    self.attacker = self.make_system("attacker", "10.0.0.9")

  def make_system(self, name, ip):
    system = System.objects.create(hostname=name, created_by=self.user, provision=False)
    NetworkInterface.objects.create(system=system, name="eth0", ipaddress=ip, bootable=True)
    return system

  def get_self(self, remote_addr, xff=None):
    meta = {"REMOTE_ADDR": remote_addr}
    if xff is not None:
      meta["HTTP_X_FORWARDED_FOR"] = xff
    return self.client.get("/systems/?self", CONTENT_TYPE="application/json", **meta)

  def post_self(self, body, remote_addr, xff=None):
    meta = {"REMOTE_ADDR": remote_addr}
    if xff is not None:
      meta["HTTP_X_FORWARDED_FOR"] = xff
    return self.client.post("/systems/?self", json.dumps(body), content_type="application/json", **meta)

  def hostnames(self, response):
    self.assertEqual(response.status_code, 200, response.content)
    return [system["hostname"] for system in response.json()]

  def test_get_ignores_forged_header(self):
    self.assertEqual(self.hostnames(self.get_self("10.0.0.9", xff="10.0.0.8")), ["attacker"])

  def test_get_without_header_uses_peer(self):
    self.assertEqual(self.hostnames(self.get_self("10.0.0.8")), ["victim"])

  def test_get_from_unknown_peer_is_404_despite_header(self):
    self.assertEqual(self.get_self("10.0.0.50", xff="10.0.0.8").status_code, 404)

  def test_post_ignores_forged_header(self):
    # setting the netboot flag on a stateful node makes it reinstall.
    response = self.post_self({"netboot": True}, "10.0.0.9", xff="10.0.0.8")
    self.assertEqual(response.status_code, 200, response.content)
    self.victim.refresh_from_db()
    self.attacker.refresh_from_db()
    self.assertFalse(self.victim.provision)
    self.assertTrue(self.attacker.provision)

  def test_post_from_unknown_peer_is_404_despite_header(self):
    self.assertEqual(self.post_self({"netboot": True}, "10.0.0.50", xff="10.0.0.8").status_code, 404)
    self.victim.refresh_from_db()
    self.assertFalse(self.victim.provision)

  @override_settings(TRUSTED_PROXIES=["10.0.0.1"])
  def test_trusted_proxy_header_is_honored(self):
    self.assertEqual(self.hostnames(self.get_self("10.0.0.1", xff="10.0.0.8")), ["victim"])
    response = self.post_self({"netboot": True}, "10.0.0.1", xff="10.0.0.8")
    self.assertEqual(response.status_code, 200, response.content)
    self.victim.refresh_from_db()
    self.assertTrue(self.victim.provision)
