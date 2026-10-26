import json
from unittest import mock

from django.contrib.auth.models import User
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.forms import inlineformset_factory
from django.test import TestCase, TransactionTestCase

from common.testing import APITestCase
from osmanagement.models import OSDistro
from systems.admin import NetForm, NetworkInterfaceInlineFormset, SystemAdmin
from systems.models import System, SystemImage, NetworkInterface, SystemBMC
from systems.views import SystemPowerAPIView

LOCAL_BOOT = "System not set to provision, or has no bootable NIC"


class ProvisionTestCase(TestCase):
  """ A system with an image, ready to PXE boot. """

  def setUp(self):
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.distro = OSDistro.objects.create(
      name="test-distro", vendor="test", version="9", baseurl="http://localhost/",
      install_kernel_cmdline="quiet", initial_mods="e1000", prov_interface="eth0", tmpfs_root_size=8,
    )
    self.image = SystemImage.objects.create(name="test-image", created_by=self.user, osdistro=self.distro)
    self.system = System.objects.create(hostname="prov-node", created_by=self.user, systemimage=self.image)

  def get_ipxe(self, ip):
    response = self.client.get("/ipxe/", REMOTE_ADDR=ip)
    self.assertEqual(response.status_code, 200)
    return response.content.decode()

  def assertNetboots(self, content):
    self.assertIn(f"kernel /images/{self.image.slug}.vmlinuz", content)
    self.assertNotIn(LOCAL_BOOT, content)

  def assertLocalBoots(self, content):
    self.assertIn(LOCAL_BOOT, content)
    self.assertNotIn("kernel /images/", content)


class ProvisionDefaultTests(ProvisionTestCase):

  def test_new_system_is_set_to_provision(self):
    self.assertTrue(self.system.provision)


class IPXEProvisionTests(ProvisionTestCase):
  """ /ipxe/ netboots only a system set to provision, from its bootable NIC. """

  def test_provision_with_bootable_nic_netboots(self):
    NetworkInterface.objects.create(system=self.system, name="eth0", ipaddress="10.0.0.10", bootable=True)
    self.assertNetboots(self.get_ipxe("10.0.0.10"))

  def test_not_provisioned_boots_locally(self):
    NetworkInterface.objects.create(system=self.system, name="eth0", ipaddress="10.0.0.11", bootable=True)
    self.system.provision = False
    self.system.save()
    self.assertLocalBoots(self.get_ipxe("10.0.0.11"))

  def test_provision_without_bootable_nic_boots_locally(self):
    # an installed stateful system must not be reinstalled just because provision is set.
    NetworkInterface.objects.create(system=self.system, name="eth0", ipaddress="10.0.0.12", bootable=False)
    self.assertLocalBoots(self.get_ipxe("10.0.0.12"))

  def test_not_provisioned_skips_custom_ipxe(self):
    self.image.customIPXE = "#!ipxe\necho custom"
    self.image.save()
    NetworkInterface.objects.create(system=self.system, name="eth0", ipaddress="10.0.0.13", bootable=True)
    self.system.provision = False
    self.system.save()
    content = self.get_ipxe("10.0.0.13")
    self.assertNotIn("echo custom", content)
    self.assertLocalBoots(content)

  def test_shared_ip_uses_the_bootable_nic(self):
    other = System.objects.create(hostname="other-node", created_by=self.user, systemimage=self.image)
    NetworkInterface.objects.create(system=other, name="eth0", ipaddress="10.0.0.14", bootable=False)
    NetworkInterface.objects.create(system=self.system, name="eth1", ipaddress="10.0.0.14", bootable=True)
    self.assertNetboots(self.get_ipxe("10.0.0.14"))

  def test_nads_boot_ignores_provision(self):
    SystemImage.objects.create(name="__nads__", created_by=self.user, osdistro=self.distro)
    self.assertIn("kernel /images/nads.vmlinuz", self.get_ipxe("10.0.0.99"))


class OneBootableNICTests(ProvisionTestCase):
  """ A system has at most one bootable NIC. """

  def test_saving_a_bootable_nic_clears_the_others(self):
    eth0 = NetworkInterface.objects.create(system=self.system, name="eth0", bootable=True)
    eth1 = NetworkInterface.objects.create(system=self.system, name="eth1", bootable=True)
    eth0.refresh_from_db()
    self.assertFalse(eth0.bootable)
    self.assertTrue(eth1.bootable)

  def test_other_systems_keep_their_bootable_nic(self):
    other = System.objects.create(hostname="other-node", created_by=self.user)
    theirs = NetworkInterface.objects.create(system=other, name="eth0", bootable=True)
    NetworkInterface.objects.create(system=self.system, name="eth0", bootable=True)
    theirs.refresh_from_db()
    self.assertTrue(theirs.bootable)

  def formset(self, *bootable):
    # NetForm, as the admin inline uses, so "on" ticks the nullable bootable field.
    FormSet = inlineformset_factory(System, NetworkInterface, form=NetForm, formset=NetworkInterfaceInlineFormset,
                                    fields=["name", "bootable", "switch_port"], extra=0)
    data = {"networkinterface_set-TOTAL_FORMS": str(len(bootable)), "networkinterface_set-INITIAL_FORMS": "0"}
    for i, flag in enumerate(bootable):
      data[f"networkinterface_set-{i}-name"] = f"eth{i}"
      if flag:
        data[f"networkinterface_set-{i}-bootable"] = "on"
    return FormSet(data, instance=self.system)

  def test_admin_inline_rejects_two_bootable_nics(self):
    formset = self.formset(True, True)
    self.assertFalse(formset.is_valid())
    self.assertIn("Only one network interface can be bootable.", formset.non_form_errors())

  def test_admin_inline_accepts_one_bootable_nic(self):
    formset = self.formset(True, False)
    self.assertTrue(formset.is_valid(), formset.errors)


class SelfNetbootTests(ProvisionTestCase):
  """ POST /systems/?self {"netboot": ...} from the node itself. """

  def setUp(self):
    super().setUp()
    self.client.force_login(self.user)
    self.eth0 = NetworkInterface.objects.create(system=self.system, name="eth0", ipaddress="10.0.0.20", bootable=True)
    self.eth1 = NetworkInterface.objects.create(system=self.system, name="eth1", ipaddress="10.0.1.20")

  def post_self(self, body, ip="10.0.0.20"):
    return self.client.post("/systems/?self", json.dumps(body), content_type="application/json", REMOTE_ADDR=ip)

  def test_netboot_false_clears_provision(self):
    # what static/mprov_stateful.py sends once it has installed.
    response = self.post_self({"netboot": False})
    self.assertEqual(response.status_code, 200, response.content)
    self.assertEqual(response.json(), {"provision": False, "bootable_nic": "eth0"})
    self.system.refresh_from_db()
    self.assertFalse(self.system.provision)
    # the boot NIC is kept, so a PXE Boot can provision it again.
    self.eth0.refresh_from_db()
    self.assertTrue(self.eth0.bootable)

  def test_installed_system_then_boots_locally(self):
    self.post_self({"netboot": False})
    self.assertLocalBoots(self.get_ipxe("10.0.0.20"))

  def test_netboot_true_sets_provision_and_boot_nic(self):
    self.system.provision = False
    self.system.save()
    response = self.post_self({"netboot": True}, ip="10.0.1.20")
    self.assertEqual(response.status_code, 200, response.content)
    self.assertEqual(response.json(), {"provision": True, "bootable_nic": "eth1"})
    self.system.refresh_from_db()
    self.assertTrue(self.system.provision)
    self.eth0.refresh_from_db()
    self.eth1.refresh_from_db()
    self.assertFalse(self.eth0.bootable)
    self.assertTrue(self.eth1.bootable)
    self.assertNetboots(self.get_ipxe("10.0.1.20"))

  def test_string_values_are_accepted(self):
    self.assertEqual(self.post_self({"netboot": "false"}).status_code, 200)
    self.system.refresh_from_db()
    self.assertFalse(self.system.provision)

  def test_non_boolean_is_400_and_changes_nothing(self):
    response = self.post_self({"netboot": "maybe"})
    self.assertEqual(response.status_code, 400)
    self.system.refresh_from_db()
    self.assertTrue(self.system.provision)

  def test_other_key_is_403_and_changes_nothing(self):
    response = self.post_self({"netboot": False, "hostname": "evil"})
    self.assertEqual(response.status_code, 403)
    self.system.refresh_from_db()
    self.assertTrue(self.system.provision)
    self.assertEqual(self.system.hostname, "prov-node")

  def test_unknown_ip_is_404_with_json_detail(self):
    response = self.post_self({"netboot": False}, ip="10.9.9.9")
    self.assertEqual(response.status_code, 404)
    # a JSON object, not a double-encoded string.
    self.assertIn("10.9.9.9", response.json()["detail"])

  def test_anonymous_is_rejected(self):
    self.client.logout()
    self.assertIn(self.post_self({"netboot": False}).status_code, (401, 403))
    self.system.refresh_from_db()
    self.assertTrue(self.system.provision)


class PXEBootProvisionTests(ProvisionTestCase):
  """ The PXE Boot buttons and actions set provision, and refuse a system with no bootable NIC. """

  def setUp(self):
    super().setUp()
    self.client.force_login(self.user)
    self.system.provision = False
    self.system.save()
    self.nic = NetworkInterface.objects.create(system=self.system, name="eth0", ipaddress="10.0.0.30", bootable=True)
    self.bmc = SystemBMC.objects.create(system=self.system, ipaddress="10.0.2.30", username="admin", password="pw")
    self.bare = System.objects.create(hostname="prov-bare", created_by=self.user, systemimage=self.image, provision=False)
    NetworkInterface.objects.create(system=self.bare, name="eth0", ipaddress="10.0.0.31", bootable=False)
    self.bare_bmc = SystemBMC.objects.create(system=self.bare, ipaddress="10.0.2.31", username="admin", password="pw")
    patcher = mock.patch.object(SystemPowerAPIView, "_doPowerCmd", return_value={"status": 200})
    self.power = patcher.start()
    self.addCleanup(patcher.stop)

  def get_json(self, url):
    return self.client.get(url, CONTENT_TYPE="application/json")

  def assertProvision(self, system, expected):
    system.refresh_from_db()
    self.assertEqual(system.provision, expected)

  def test_pxe_button_sets_provision(self):
    for action in ("pxe", "pxeefi"):
      with self.subTest(action=action):
        self.system.provision = False
        self.system.save()
        response = self.get_json(f"/power/{action}/?id={self.system.id}")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertProvision(self.system, True)
        self.power.assert_called_with(self.bmc, action)

  def test_pxe_button_without_bootable_nic_is_an_error_and_no_reset(self):
    for action in ("pxe", "pxeefi"):
      with self.subTest(action=action):
        response = self.get_json(f"/power/{action}/?id={self.bare.id}")
        self.assertEqual(response.status_code, 409)
        self.assertIn("no bootable network interface", response.json()["details"])
        self.assertProvision(self.bare, False)
    self.power.assert_not_called()

  def test_other_power_actions_leave_provision_alone(self):
    for action in ("on", "off", "cycle", "reset", "status"):
      self.get_json(f"/power/{action}/?id={self.system.id}")
    self.assertProvision(self.system, False)

  def test_pxe_by_hostname_skips_systems_without_bootable_nic(self):
    # mash's `bmc power pxe` goes through ?hostname=.
    response = self.get_json("/power/pxe/?hostname=prov-")
    self.assertEqual(response.status_code, 200)
    body = response.json()
    self.assertEqual(body[str(self.bmc)], {"status": 200})
    self.assertEqual(body[str(self.bare_bmc)]["status"], 409)
    self.power.assert_called_once_with(self.bmc, "pxe")
    self.assertProvision(self.system, True)
    self.assertProvision(self.bare, False)

  def test_pxe_by_bmc_filter_skips_systems_without_bootable_nic(self):
    response = self.get_json(f"/power/pxe/?ipaddress={self.bare_bmc.ipaddress}")
    self.assertEqual(response.json()[str(self.bare_bmc)]["status"], 409)
    self.power.assert_not_called()

  def run_admin_action(self, action, *systems):
    data = {"action": action, "_selected_action": [s.pk for s in systems]}
    with mock.patch.object(SystemAdmin, "_doPowerCmd") as power:
      response = self.client.post("/admin/systems/system/", data, follow=True)
    self.assertEqual(response.status_code, 200)
    return power, [str(m) for m in response.context["messages"]]

  def test_admin_pxe_actions(self):
    for action, power_action in (("sys_pxe", "pxe"), ("sys_pxe_efi", "pxeefi")):
      with self.subTest(action=action):
        self.system.provision = False
        self.system.save()
        power, messages = self.run_admin_action(action, self.system, self.bare)
        power.assert_called_once_with(self.bmc, power_action)
        self.assertProvision(self.system, True)
        self.assertProvision(self.bare, False)
        self.assertTrue(any("prov-bare has no bootable network interface" in m for m in messages), messages)


class ProvisionAPITests(APITestCase):
  """ provision is a normal System field on the API. """

  def setUp(self):
    super().setUp()
    self.system = System.objects.create(hostname="api-node", created_by=self.user)

  def test_detail_includes_provision(self):
    self.assertIs(self.get_json(f"/systems/{self.system.pk}/").json()["provision"], True)

  def test_patch_provision(self):
    response = self.client.patch(f"/systems/{self.system.pk}/", json.dumps({"provision": False}),
                                 content_type="application/json")
    self.assertEqual(response.status_code, 200, response.content)
    self.system.refresh_from_db()
    self.assertFalse(self.system.provision)

  def test_admin_change_form_shows_provision(self):
    response = self.client.get(f"/admin/systems/system/{self.system.pk}/change/")
    self.assertContains(response, 'name="provision"')


class ProvisionMigrationTests(TransactionTestCase):
  """ 0071 sets provision from the bootable NICs and keeps at most one per system. """

  migrate_from = [("systems", "0069_fix_config_params_default")]
  migrate_to = [("systems", "0071_provision_from_bootable_nics")]

  def setUp(self):
    executor = MigrationExecutor(connection)
    executor.migrate(self.migrate_from)
    apps = executor.loader.project_state(self.migrate_from).apps
    user = apps.get_model("auth", "User").objects.create(username="migrator")
    OldSystem = apps.get_model("systems", "System")
    OldNIC = apps.get_model("systems", "NetworkInterface")
    self.installed = OldSystem.objects.create(hostname="installed", created_by=user).pk
    OldNIC.objects.create(system_id=self.installed, name="eth0", bootable=False)
    self.netboot = OldSystem.objects.create(hostname="netboot", created_by=user).pk
    OldNIC.objects.create(system_id=self.netboot, name="eth0", bootable=True)
    self.multi = OldSystem.objects.create(hostname="multi", created_by=user, prov_interface="eth1").pk
    for name in ("eth0", "eth1", "eth2"):
      OldNIC.objects.create(system_id=self.multi, name=name, bootable=True)
    self.multi_noprov = OldSystem.objects.create(hostname="multi-noprov", created_by=user).pk
    for name in ("eth0", "eth1"):
      OldNIC.objects.create(system_id=self.multi_noprov, name=name, bootable=True)

    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(self.migrate_to)
    self.apps = executor.loader.project_state(self.migrate_to).apps

  def tearDown(self):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes())

  def provision(self, pk):
    return self.apps.get_model("systems", "System").objects.get(pk=pk).provision

  def bootable(self, pk):
    NIC = self.apps.get_model("systems", "NetworkInterface")
    return list(NIC.objects.filter(system_id=pk, bootable=True).values_list("name", flat=True))

  def test_system_without_bootable_nic_is_not_provisioned(self):
    self.assertFalse(self.provision(self.installed))

  def test_system_with_bootable_nic_is_provisioned(self):
    self.assertTrue(self.provision(self.netboot))
    self.assertEqual(self.bootable(self.netboot), ["eth0"])

  def test_keeps_the_prov_interface_nic(self):
    self.assertTrue(self.provision(self.multi))
    self.assertEqual(self.bootable(self.multi), ["eth1"])

  def test_keeps_the_oldest_nic_without_prov_interface(self):
    self.assertEqual(self.bootable(self.multi_noprov), ["eth0"])
