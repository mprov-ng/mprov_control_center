from django.contrib.auth.models import Permission, User

from networks.models import SwitchPort
from networks.testing import NetworkTestCase
from systems.models import NetworkInterface, System

CHANGELIST = "/admin/networks/switchport/"


class SwitchPortAdminTests(NetworkTestCase):
  """ The Switch Ports list, and its bulk "Set network" action (#577). """

  def setUp(self):
    super().setUp()
    self.sw1 = self.switch("sw01", self.mgmt)
    self.sw2 = self.switch("sw02", self.mgmt)
    self.p1 = SwitchPort.objects.create(name="1/1", switch=self.sw1)
    self.p2 = SwitchPort.objects.create(name="1/2", switch=self.sw1, networks=self.mgmt)
    self.p3 = SwitchPort.objects.create(name="1/1", switch=self.sw2)
    node = System.objects.create(hostname="node01", created_by=self.user)
    NetworkInterface.objects.create(system=node, name="ens18", switch_port=self.p1, network=self.lan)

  def act(self, ports, **extra):
    return self.client.post(CHANGELIST, {"action": "set_network", "_selected_action": [p.pk for p in ports],
                                         **extra})

  def messages(self, response):
    return [(m.level_tag, str(m)) for m in response.context["messages"]]

  def test_list_shows_switch_network_and_interface(self):
    response = self.client.get(CHANGELIST)
    self.assertEqual(response.status_code, 200)
    self.assertContains(response, "node01: ens18")
    self.assertContains(response, "sw02")
    response = self.client.get(f"{CHANGELIST}?networks__id__exact={self.mgmt.pk}")
    self.assertEqual(list(response.context["cl"].result_list), [self.p2])
    response = self.client.get(f"{CHANGELIST}?q=sw02")
    self.assertEqual(list(response.context["cl"].result_list), [self.p3])

  def test_action_asks_for_the_network_first(self):
    response = self.act([self.p1, self.p3])
    self.assertEqual(response.status_code, 200)
    self.assertTemplateUsed(response, "admin/networks/switchport/set_network.html")
    self.assertContains(response, 'name="network"')
    self.assertContains(response, f'name="_selected_action" value="{self.p1.pk}"')
    self.assertContains(response, f'name="_selected_action" value="{self.p3.pk}"')
    self.assertIsNone(SwitchPort.objects.get(pk=self.p1.pk).networks)

  def test_action_sets_the_network_of_the_selected_ports_only(self):
    response = self.act([self.p1, self.p2], apply="Set network", network=self.lan.pk)
    self.assertRedirects(response, CHANGELIST, fetch_redirect_response=False)
    networks = {p.pk: p.networks for p in SwitchPort.objects.all()}
    self.assertEqual(networks, {self.p1.pk: self.lan, self.p2.pk: self.lan, self.p3.pk: None})
    response = self.client.get(response["Location"])
    self.assertIn(("success", "Set the network of 2 switch ports to Cluster LAN."), self.messages(response))

  def test_ports_already_on_the_network_are_not_counted(self):
    response = self.act([self.p2, self.p3], apply="Set network", network=self.mgmt.pk)
    response = self.client.get(response["Location"])
    self.assertIn(("success", "Set the network of 1 switch port to Mgmt."), self.messages(response))

  def test_a_network_is_required(self):
    response = self.act([self.p1], apply="Set network", network="")
    self.assertEqual(response.status_code, 200)
    self.assertTrue(response.context["form"].errors)
    self.assertIsNone(SwitchPort.objects.get(pk=self.p1.pk).networks)

  def test_needs_change_permission(self):
    viewer = User.objects.create_user("viewer", password="password", is_staff=True)
    viewer.user_permissions.add(Permission.objects.get(codename="view_switchport"))
    self.client.force_login(viewer)
    response = self.client.get(CHANGELIST)
    self.assertEqual(response.status_code, 200)
    self.assertNotContains(response, 'value="set_network"')
    self.act([self.p1], apply="Set network", network=self.lan.pk)
    self.assertIsNone(SwitchPort.objects.get(pk=self.p1.pk).networks)
