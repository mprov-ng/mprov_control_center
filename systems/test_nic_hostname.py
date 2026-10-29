import json

from django.contrib.auth.models import User
from django.test import TestCase

from systems.models import System, NetworkInterface


class NetworkInterfaceHostnameTests(TestCase):
  """ A NIC's hostname is always its System's: read-only in the API, and kept
  in step when the System is renamed (#382). DHCP/DNS and register_IPv6_ll.py
  depend on the two matching. """

  def setUp(self):
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    self.system = System.objects.create(hostname="node01", created_by=self.user)
    self.nic = NetworkInterface.objects.create(system=self.system, name="ens18")

  def write_json(self, method, url, data):
    return getattr(self.client, method)(url, json.dumps(data), content_type="application/json")

  def test_post_ignores_hostname(self):
    response = self.write_json("post", "/networkinterfaces/",
      {"system": self.system.id, "name": "ib0", "hostname": "something-else"})
    self.assertEqual(response.status_code, 201, response.content)
    self.assertEqual(response.json()["hostname"], "node01")
    self.assertEqual(NetworkInterface.objects.get(name="ib0").hostname, "node01")

  def test_patch_ignores_hostname(self):
    response = self.write_json("patch", f"/networkinterfaces/{self.nic.id}/", {"hostname": "something-else"})
    self.assertEqual(response.status_code, 200, response.content)
    self.nic.refresh_from_db()
    self.assertEqual(self.nic.hostname, "node01")

  def test_rename_updates_nics(self):
    other = NetworkInterface.objects.create(system=self.system, name="ib0")
    self.system.hostname = "node02"
    self.system.save()
    for nic in (self.nic, other):
      nic.refresh_from_db()
      self.assertEqual(nic.hostname, "node02")

  def test_rename_through_api_updates_nics(self):
    response = self.write_json("patch", f"/systems/{self.system.id}/", {"hostname": "node03"})
    self.assertEqual(response.status_code, 200, response.content)
    self.nic.refresh_from_db()
    self.assertEqual(self.nic.hostname, "node03")
    response = self.client.get("/networkinterfaces/?hostname=node03", CONTENT_TYPE="application/json")
    self.assertEqual([nic["id"] for nic in response.json()], [self.nic.id])

  def test_rename_leaves_other_systems_alone(self):
    other_system = System.objects.create(hostname="node09", created_by=self.user)
    other_nic = NetworkInterface.objects.create(system=other_system, name="ens18")
    self.system.hostname = "node02"
    self.system.save()
    other_nic.refresh_from_db()
    self.assertEqual(other_nic.hostname, "node09")
