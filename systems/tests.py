import io
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase
from systems.views import SystemPowerAPIView
from django.test import TestCase
from django.contrib.auth.models import User
from osmanagement.models import OSDistro
from systems.models import System, SystemGroup, SystemImage, NetworkInterface, SystemBMC, SystemBMCForm

class SystemPowerAPIViewResetTests(SimpleTestCase):
  """ The reset action hard resets, and only power cycles if the hard reset fails. """

  def setUp(self):
    self.bmc = SimpleNamespace(ipaddress="10.0.0.1", username="admin", password="secret")
    patcher = mock.patch("systems.views.pyipmi")
    self.pyipmi = patcher.start()
    self.addCleanup(patcher.stop)
    self.ipmi = self.pyipmi.create_connection.return_value

  def test_reset_does_not_power_cycle_after_hard_reset(self):
    SystemPowerAPIView()._doPowerCmd(self.bmc, "reset")
    self.ipmi.chassis_control_hard_reset.assert_called_once_with()
    self.ipmi.chassis_control_power_cycle.assert_not_called()

  def test_reset_power_cycles_when_hard_reset_fails(self):
    self.ipmi.chassis_control_hard_reset.side_effect = Exception("not supported")
    SystemPowerAPIView()._doPowerCmd(self.bmc, "reset")
    self.ipmi.chassis_control_power_cycle.assert_called_once_with()

  @mock.patch("systems.views.subprocess")
  def test_pxe_resets_once(self, subprocess):
    # pxe sets the boot device, then forces a reset.
    SystemPowerAPIView()._doPowerCmd(self.bmc, "pxe")
    subprocess.run.assert_called_once()
    self.ipmi.chassis_control_hard_reset.assert_called_once_with()
    self.ipmi.chassis_control_power_cycle.assert_not_called()

  @mock.patch("systems.views.subprocess")
  def test_pxe_passes_password_in_env(self, subprocess):
    # the password must not be on the ipmitool command line, where ps shows it.
    SystemPowerAPIView()._doPowerCmd(self.bmc, "pxeefi")
    args = subprocess.run.call_args.kwargs["args"]
    env = subprocess.run.call_args.kwargs["env"]
    self.assertIn("-E", args)
    self.assertEqual(args[-1], "options=efiboot")
    self.assertFalse(any("secret" in arg for arg in args))
    self.assertEqual(env["IPMI_PASSWORD"], "secret")

  @mock.patch("systems.views.subprocess")
  def test_power_cmd_does_not_print_password(self, subprocess):
    out = io.StringIO()
    with redirect_stdout(out):
      SystemPowerAPIView()._doPowerCmd(self.bmc, "pxe")
    self.assertNotIn("secret", out.getvalue())


class SystemBMCPasswordTests(TestCase):
  """ The BMC password is write-only, except for a single entry or ?detail, which
  mprov_scripts' setupBMC.py reads. """

  def setUp(self):
    self.user = User.objects.create(username="bmc-test")
    self.system = System.objects.create(hostname="bmc-node", created_by=self.user)
    self.bmc = SystemBMC.objects.create(system=self.system, ipaddress="10.0.1.5", username="admin", password="bmc-secret")
    self.client.force_login(self.user)

  def get_json(self, url):
    return self.client.get(url, CONTENT_TYPE="application/json")

  def test_list_omits_password(self):
    response = self.get_json("/systembmcs/")
    self.assertEqual(response.status_code, 200)
    self.assertNotIn("password", response.json()[0])
    self.assertNotIn("bmc-secret", response.content.decode())

  def test_detail_returns_password(self):
    response = self.get_json(f"/systembmcs/?system={self.system.id}&detail")
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json()[0]["password"], "bmc-secret")

  def test_single_entry_returns_password(self):
    response = self.get_json(f"/systembmcs/{self.bmc.id}/")
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json()["password"], "bmc-secret")

  def test_patch_sets_password_without_echo_or_print(self):
    out = io.StringIO()
    with redirect_stdout(out):
      response = self.client.patch(f"/systembmcs/{self.bmc.id}/", data='{"password": "new-secret"}', content_type="application/json")
    self.assertEqual(response.status_code, 200)
    self.assertNotIn("password", response.json())
    self.assertNotIn("new-secret", out.getvalue())
    self.bmc.refresh_from_db()
    self.assertEqual(self.bmc.password, "new-secret")

  def test_admin_form_does_not_print_password(self):
    form = SystemBMCForm(data={"system": self.system.id, "ipaddress": "10.0.1.6", "password": "form-secret", "vlan": 0})
    out = io.StringIO()
    with redirect_stdout(out):
      self.assertTrue(form.is_valid(), form.errors)
    self.assertNotIn("form-secret", out.getvalue())



class IPXEAPIViewTests(TestCase):
  """ /ipxe/ looks up the NIC by the client IP and renders the ipxe template. """

  def setUp(self):
    self.user = User.objects.create(username="ipxe-test")
    self.distro = OSDistro.objects.create(
      name="test-distro", vendor="test", version="9", baseurl="http://localhost/",
      install_kernel_cmdline="quiet", initial_mods="e1000", prov_interface="eth0", tmpfs_root_size=8,
    )
    self.image = SystemImage.objects.create(name="test-image", created_by=self.user, osdistro=self.distro)
    self.system = System.objects.create(hostname="ipxe-node", created_by=self.user, systemimage=self.image)

  def get_ipxe(self, ip):
    return self.client.get("/ipxe/", REMOTE_ADDR=ip)

  def test_no_bootable_nic_renders_local_boot(self):
    # the state the stateful installer leaves a system in before it reboots.
    NetworkInterface.objects.create(system=self.system, name="eth0", ipaddress="10.0.0.5", bootable=False)
    response = self.get_ipxe("10.0.0.5")
    self.assertEqual(response.status_code, 200)
    content = response.content.decode()
    self.assertIn("System not set to bootable", content)
    self.assertNotIn("kernel /images/", content)

  def test_bootable_nic_renders_kernel(self):
    NetworkInterface.objects.create(system=self.system, name="eth0", ipaddress="10.0.0.6", bootable=True)
    response = self.get_ipxe("10.0.0.6")
    self.assertEqual(response.status_code, 200)
    content = response.content.decode()
    self.assertIn(f"kernel /images/{self.image.slug}.vmlinuz", content)
    self.assertNotIn("System not set to bootable", content)

  def test_image_without_distro_renders_kernel(self):
    image = SystemImage.objects.create(name="no-distro-image", created_by=self.user)
    system = System.objects.create(hostname="no-distro-node", created_by=self.user, systemimage=image)
    NetworkInterface.objects.create(system=system, name="eth0", ipaddress="10.0.0.7", bootable=True)
    response = self.get_ipxe("10.0.0.7")
    self.assertEqual(response.status_code, 200)
    self.assertIn(f"kernel /images/{image.slug}.vmlinuz", response.content.decode())

  def test_unknown_ip_without_nads_image_is_404(self):
    response = self.get_ipxe("10.0.0.99")
    self.assertEqual(response.status_code, 404)

  def test_unknown_ip_boots_nads_image(self):
    image = SystemImage.objects.create(name="__nads__", created_by=self.user, osdistro=self.distro)
    response = self.get_ipxe("10.0.0.99")
    self.assertEqual(response.status_code, 200)
    self.assertIn(f"kernel /images/{image.slug}.vmlinuz", response.content.decode())


class FlattenConfigTests(TestCase):
  """ System.config is built from OS Distro -> System Groups (by name) -> System.
  install_kernel_cmdline and initial_mods append unless prefixed with '=', everything
  else overwrites when set. """

  def setUp(self):
    self.user = User.objects.create(username="flatten-test")
    self.distro = OSDistro.objects.create(
      name="test-distro", vendor="test", version="9", baseurl="http://localhost/",
      install_kernel_cmdline="quiet", initial_mods="e1000", prov_interface="eth0", tmpfs_root_size=8,
    )
    self.image = SystemImage.objects.create(name="test-image", created_by=self.user, osdistro=self.distro)
    self.group_a = SystemGroup.objects.create(name="a-group", install_kernel_cmdline="console=ttyS0", initial_mods="mlx5_core")
    self.group_b = SystemGroup.objects.create(name="b-group", prov_interface="ib0", tmpfs_root_size=16)

  def make_system(self, hostname, groups=(), **kwargs):
    system = System.objects.create(hostname=hostname, created_by=self.user, **kwargs)
    system.systemgroups.add(*groups)
    # config is flattened on load, so re-fetch after the groups are attached.
    return System.objects.get(pk=system.pk)

  def test_distro_only(self):
    system = self.make_system("distro-only", systemimage=self.image)
    self.assertEqual(system.config["install_kernel_cmdline"], "quiet")
    self.assertEqual(system.config["initial_mods"], "e1000")
    self.assertEqual(system.config["prov_interface"], "eth0")
    self.assertEqual(system.config["tmpfs_root_size"], 8)

  def test_appends_and_overwrites_through_hierarchy(self):
    system = self.make_system(
      "full-stack", groups=[self.group_a, self.group_b], systemimage=self.image,
      install_kernel_cmdline="nomodeset", initial_mods="ixgbe",
    )
    self.assertEqual(system.config["install_kernel_cmdline"], "quiet console=ttyS0 nomodeset")
    self.assertEqual(system.config["initial_mods"], "e1000,mlx5_core,ixgbe")
    self.assertEqual(system.config["prov_interface"], "ib0")
    self.assertEqual(system.config["tmpfs_root_size"], 16)

  def test_system_overwrites(self):
    system = self.make_system(
      "overwrite", groups=[self.group_a, self.group_b], systemimage=self.image,
      install_kernel_cmdline="=single", initial_mods="=virtio_net", prov_interface="eno1", tmpfs_root_size=32,
    )
    self.assertEqual(system.config["install_kernel_cmdline"], "single")
    self.assertEqual(system.config["initial_mods"], "virtio_net")
    self.assertEqual(system.config["prov_interface"], "eno1")
    self.assertEqual(system.config["tmpfs_root_size"], 32)

  def test_group_overwrite_then_system_append(self):
    group = SystemGroup.objects.create(name="c-group", install_kernel_cmdline="=rd.break")
    system = self.make_system("group-overwrite", groups=[group], systemimage=self.image, install_kernel_cmdline="nomodeset")
    self.assertEqual(system.config["install_kernel_cmdline"], "rd.break nomodeset")

  def test_groups_apply_in_name_order(self):
    group_z = SystemGroup.objects.create(name="z-group", prov_interface="eth9")
    system = self.make_system("group-order", groups=[group_z, self.group_b], systemimage=self.image)
    self.assertEqual(system.config["prov_interface"], "eth9")

  def test_reload_does_not_accumulate(self):
    system = self.make_system("reload", groups=[self.group_a], install_kernel_cmdline="nomodeset", initial_mods="ixgbe")
    for _ in range(3):
      system = System.objects.get(pk=system.pk)
    self.assertEqual(system.config["install_kernel_cmdline"], "console=ttyS0 nomodeset")
    self.assertEqual(system.config["initial_mods"], "mlx5_core,ixgbe")

  def test_no_leak_between_systems(self):
    first = self.make_system("first", groups=[self.group_a, self.group_b], systemimage=self.image)
    second = self.make_system("second")
    self.assertIsNot(first.config, second.config)
    self.assertNotIn("prov_interface", second.config)
    self.assertNotIn("install_kernel_cmdline", second.config)
    self.assertEqual(first.config["prov_interface"], "ib0")

  def test_append_without_distro(self):
    system = self.make_system("no-distro", install_kernel_cmdline="console=tty0", initial_mods="ixgbe")
    self.assertEqual(system.config["install_kernel_cmdline"], "console=tty0")
    self.assertEqual(system.config["initial_mods"], "ixgbe")

  def test_queryset_instances_keep_their_own_config(self):
    self.make_system("list-a", groups=[self.group_b], systemimage=self.image)
    self.make_system("list-b", prov_interface="eno2")
    configs = {s.hostname: s.config for s in System.objects.all()}
    self.assertEqual(configs["list-a"]["prov_interface"], "ib0")
    self.assertEqual(configs["list-b"]["prov_interface"], "eno2")
