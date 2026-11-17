import json

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.forms import inlineformset_factory
from django.test import TestCase

from pki.test_auth import AgentTestCase
from systems.admin import NetForm, NetworkInterfaceInlineFormset
from systems.models import NIC_NAME_TAKEN, NetworkInterface, System


class NICNameUniqueTests(TestCase):
  """ A system's NICs have different names, ignoring case (MariaDB compares
  them that way): the API answers a clash with a 400 on name, the admin with
  a form error, and the database refuses an exact duplicate outright (#581). """

  def setUp(self):
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    self.system = System.objects.create(hostname="node01", created_by=self.user)
    self.other = System.objects.create(hostname="node02", created_by=self.user)
    self.eth0 = NetworkInterface.objects.create(system=self.system, name="eth0")
    self.ib0 = NetworkInterface.objects.create(system=self.system, name="ib0")

  def write(self, method, url, data):
    return getattr(self.client, method)(url, json.dumps(data), content_type="application/json")

  def assertNameTaken(self, response):
    self.assertEqual(response.status_code, 400, response.content)
    self.assertEqual(response.json(), {"name": [NIC_NAME_TAKEN]})

  def test_post_duplicate_is_400(self):
    self.assertNameTaken(self.write("post", "/networkinterfaces/", {"system": self.system.pk, "name": "eth0"}))
    self.assertNameTaken(self.write("post", "/networkinterfaces/", {"system": self.system.pk, "name": "ETH0"}))
    self.assertEqual(NetworkInterface.objects.filter(system=self.system).count(), 2)

  def test_same_name_on_another_system_is_fine(self):
    response = self.write("post", "/networkinterfaces/", {"system": self.other.pk, "name": "eth0"})
    self.assertEqual(response.status_code, 201, response.content)

  def test_patch_rename_onto_another_nic_is_400(self):
    self.assertNameTaken(self.write("patch", f"/networkinterfaces/{self.ib0.pk}/", {"name": "eth0"}))
    self.ib0.refresh_from_db()
    self.assertEqual(self.ib0.name, "ib0")

  def test_patch_keeping_its_own_name_is_fine(self):
    response = self.write("patch", f"/networkinterfaces/{self.eth0.pk}/", {"name": "eth0", "mtu": 9000})
    self.assertEqual(response.status_code, 200, response.content)
    response = self.write("patch", f"/networkinterfaces/{self.eth0.pk}/", {"name": "ETH0"})
    self.assertEqual(response.status_code, 200, response.content)
    response = self.write("patch", f"/networkinterfaces/{self.eth0.pk}/", {"mtu": 1500})
    self.assertEqual(response.status_code, 200, response.content)

  def test_patch_moving_to_a_system_with_that_name_is_400(self):
    NetworkInterface.objects.create(system=self.other, name="ib0")
    self.assertNameTaken(self.write("patch", f"/networkinterfaces/{self.ib0.pk}/", {"system": self.other.pk}))

  def test_database_refuses_an_exact_duplicate(self):
    with self.assertRaises(IntegrityError), transaction.atomic():
      NetworkInterface.objects.create(system=self.system, name="eth0")

  def test_model_clean(self):
    with self.assertRaises(ValidationError) as caught:
      NetworkInterface(system=self.system, name="Eth0").full_clean()
    self.assertEqual(caught.exception.message_dict["name"], [NIC_NAME_TAKEN])
    NetworkInterface(system=self.other, name="eth0").full_clean()
    self.eth0.full_clean()

  def formset(self, *names):
    FormSet = inlineformset_factory(System, NetworkInterface, form=NetForm, formset=NetworkInterfaceInlineFormset,
                                    fields=["name", "bootable", "switch_port"], extra=0)
    data = {"networkinterface_set-TOTAL_FORMS": str(len(names)), "networkinterface_set-INITIAL_FORMS": "0"}
    for i, name in enumerate(names):
      data[f"networkinterface_set-{i}-name"] = name
    return FormSet(data, instance=self.other)

  def test_admin_inline_rejects_two_new_nics_with_one_name(self):
    for names in (("eth1", "eth1"), ("eth1", "ETH1")):
      formset = self.formset(*names)
      self.assertFalse(formset.is_valid(), names)

  def test_admin_inline_rejects_a_name_the_system_has(self):
    FormSet = inlineformset_factory(System, NetworkInterface, form=NetForm, formset=NetworkInterfaceInlineFormset,
                                    fields=["name", "bootable", "switch_port"], extra=0)
    formset = FormSet({"networkinterface_set-TOTAL_FORMS": "1", "networkinterface_set-INITIAL_FORMS": "0",
                       "networkinterface_set-0-name": "IB0"}, instance=self.system,
                      queryset=NetworkInterface.objects.none())
    self.assertFalse(formset.is_valid())
    self.assertEqual(formset.forms[0].errors["name"], [NIC_NAME_TAKEN])

  def test_admin_inline_accepts_different_names(self):
    self.assertTrue(self.formset("eth0", "eth1").is_valid())


class NodeNICNameTests(AgentTestCase):
  """ A node adding its own NIC under a name it already has gets a 400 on
  name, which it can tell from a 403 rule refusal (#581, #566). """

  def test_node_post_duplicate_name_is_400(self):
    response = self.as_c01("POST", "/networkinterfaces/", {"system": self.c01.pk, "name": self.nic1.name,
                                                           "mac": "52:54:00:00:00:99"})
    self.assertEqual(response.status_code, 400, response.content)
    self.assertEqual(response.json(), {"name": [NIC_NAME_TAKEN]})
