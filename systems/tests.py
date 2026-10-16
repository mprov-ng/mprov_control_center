from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase
from systems.views import SystemPowerAPIView
from django.test import TestCase
from django.contrib.auth.models import User
from osmanagement.models import OSDistro
from systems.models import System, SystemImage, NetworkInterface

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
