import json

from jobqueue.models import Job, JobModule, JobStatus
from networks.models import SwitchPort
from networks.testing import NetworkTestCase
from pki.test_auth import AgentTestCase
from systems.models import NetworkInterface, System

PENDING = 1
DNSMASQ = ("pxe-update", "dns-update", "dhcp-update")


class PortNicSyncTests(NetworkTestCase):
  """ A person's or API client's save keeps a switch port's network and its
  NIC's network the same (#578). """

  def setUp(self):
    super().setUp()
    self.sw = self.switch("sw01", self.mgmt)
    self.port = SwitchPort.objects.create(name="1/1", switch=self.sw, networks=self.lan)
    self.node = System.objects.create(hostname="node01", created_by=self.user)
    self.nic = NetworkInterface.objects.create(system=self.node, name="ens18", switch_port=self.port,
                                               network=self.lan, ipaddress="172.16.0.11")

  def patch(self, url, body):
    response = self.client.patch(url, json.dumps(body), content_type="application/json")
    self.assertEqual(response.status_code, 200, response.content[:300])
    return response

  def networks(self):
    self.port.refresh_from_db()
    self.nic.refresh_from_db()
    return self.port.networks, self.nic.network

  def test_a_port_saved_with_a_new_network_moves_its_nic(self):
    JobStatus.objects.get_or_create(pk=PENDING, defaults={"name": "PENDING"})
    for slug in DNSMASQ:
      JobModule.objects.get_or_create(slug=slug, defaults={"name": slug})
    Job.objects.all().delete()
    self.patch(f"/switchports/{self.port.pk}/", {"networks": self.mgmt.pk})
    self.assertEqual(self.networks(), (self.mgmt, self.mgmt))
    # the NIC's save queues the DNS, DHCP and PXE update like any other
    self.assertEqual(sorted(Job.objects.filter(status_id=PENDING).values_list("module__slug", flat=True)),
                     sorted(DNSMASQ))

  def test_a_nic_saved_with_a_new_network_moves_its_port(self):
    self.patch(f"/networkinterfaces/{self.nic.pk}/", {"network": self.mgmt.pk})
    self.assertEqual(self.networks(), (self.mgmt, self.mgmt))

  def test_a_nic_linked_to_a_port_puts_the_port_on_its_network(self):
    other = SwitchPort.objects.create(name="1/2", switch=self.sw, networks=self.mgmt)
    self.patch(f"/networkinterfaces/{self.nic.pk}/", {"switch_port": other.pk})
    other.refresh_from_db()
    self.assertEqual(other.networks, self.lan)

  def test_clearing_a_network_isnt_copied(self):
    self.patch(f"/switchports/{self.port.pk}/", {"networks": None})
    self.assertEqual(self.networks(), (None, self.lan))
    self.port.networks = self.lan
    self.port.save()
    self.patch(f"/networkinterfaces/{self.nic.pk}/", {"network": None})
    self.assertEqual(self.networks(), (self.lan, None))

  def test_an_unrelated_change_leaves_the_other_side(self):
    SwitchPort.objects.filter(pk=self.port.pk).update(networks=self.mgmt)
    self.patch(f"/switchports/{self.port.pk}/", {"name": "1/9"})
    self.patch(f"/networkinterfaces/{self.nic.pk}/", {"mtu": 9000})
    self.assertEqual(self.networks(), (self.mgmt, self.lan))

  def test_saves_outside_a_request_dont_sync(self):
    self.port.networks = self.mgmt
    self.port.save()
    self.assertEqual(self.networks(), (self.mgmt, self.lan))

  def test_switch_ports_bulk_action(self):
    """ #577's "Set network" saves each port, so their NICs follow. """
    response = self.client.post("/admin/networks/switchport/", {
      "action": "set_network", "_selected_action": [self.port.pk], "apply": "Set network", "network": self.mgmt.pk})
    self.assertEqual(response.status_code, 302, response.content[:2000])
    self.assertEqual(self.networks(), (self.mgmt, self.mgmt))

  def test_switch_admin_inline(self):
    response = self.client.post(f"/admin/networks/switch/{self.sw.pk}/change/", {
      "hostname": "sw01", "mgmt_ip": "10.0.0.1", "mgmt_mac": "de:ad:be:ef:00:01", "guid": "",
      "network": self.mgmt.pk,
      "timestamp_0": "2026-01-01", "timestamp_1": "00:00:00", "updated_0": "2026-01-01", "updated_1": "00:00:00",
      "switchport_set-TOTAL_FORMS": "1", "switchport_set-INITIAL_FORMS": "1",
      "switchport_set-0-id": self.port.pk, "switchport_set-0-switch": self.sw.pk,
      "switchport_set-0-name": "1/1", "switchport_set-0-networks": self.mgmt.pk})
    self.assertEqual(response.status_code, 302, response.content[:2000])
    self.assertEqual(self.networks(), (self.mgmt, self.mgmt))


class NodeSavesDontSyncTests(AgentTestCase):
  """ A node's own saves keep #575's narrower rule: linking its NIC never
  changes a port that has a network, and a port on another network is
  refused rather than synced. """

  def test_node_linking_keeps_the_ports_network(self):
    from networks.models import Switch
    switch = Switch.objects.create(hostname="sw", created_by=self.admin)
    port = SwitchPort.objects.create(name="1", switch=switch, networks=self.lan)
    self.assertEqual(self.as_c01("PATCH", f"/networkinterfaces/{self.nic1.pk}/", {"switch_port": port.pk})
                     .status_code, 200)
    port.refresh_from_db()
    self.assertEqual(port.networks, self.lan)
    # a port on another network is still refused, not synced
    other = SwitchPort.objects.create(name="2", switch=switch, networks=self.other_net)
    response = self.as_c01("PATCH", f"/networkinterfaces/{self.nic1.pk}/", {"switch_port": other.pk})
    self.assertEqual(response.status_code, 400)
    other.refresh_from_db()
    self.assertEqual(other.networks, self.other_net)
