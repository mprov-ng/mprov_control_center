from unittest import mock

from networks.models import Network, NetworkType
from networks.testing import NetworkTestCase


class NetworkSubnetChangeTests(NetworkTestCase):
  """ Changing a network's subnet in the admin goes through a confirmation page that applies the whole edit. """

  def change(self, **changes):
    data = {"name": self.lan.name, "net_type": self.net_type.pk, "vlan": self.lan.vlan, "subnet": self.lan.subnet,
            "netmask": self.lan.netmask, "domain": "", "_save": "Save"}
    data.update(changes)
    response = self.client.post(f"/admin/networks/network/{self.lan.pk}/change/", data)
    self.assertRedirects(response, f"/admin/networks/network/{self.lan.pk}/update-with-confirmation/",
                         fetch_redirect_response=False)
    return self.client.post(response["Location"], {"confirm_update": "1"}, follow=True)

  def test_other_fields_are_saved_with_the_subnet(self):
    other_type = NetworkType.objects.create(name="Infiniband")
    self.change(subnet="172.17.0.0", vlan=42, net_type=other_type.pk, isdhcp="on")
    self.lan.refresh_from_db()
    self.assertEqual((self.lan.subnet, self.lan.vlan, self.lan.net_type, self.lan.isdhcp),
                     ("172.17.0.0", 42, other_type, True))

  def test_ip_errors_are_a_warning(self):
    with mock.patch("networks.utils.update_associated_ips",
                    return_value={"interfaces_updated": 0, "bmcs_updated": 0, "errors": ["nic1: no IP"]}):
      response = self.change(subnet="172.17.0.0")
    messages = {(m.level_tag, str(m)) for m in response.context["messages"]}
    self.assertIn(("success", "Network updated successfully. "), messages)
    self.assertIn(("warning", "Errors updating IPs: nic1: no IP"), messages)
