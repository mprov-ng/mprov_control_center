from django.contrib.auth.models import User
from django.test import TestCase

from osmanagement.models import OSDistro
from systems.models import System, SystemImage, NetworkInterface


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

  def test_stateful_system(self):
    self.system.stateful = True
    self.system.save()
    NetworkInterface.objects.create(system=self.system, name="eth0", ipaddress="10.0.0.8", bootable=True)
    content = self.get_ipxe("10.0.0.8").content.decode()
    self.assertIn("mprov_stateful=1", content)
    # mprov_stateful.py finds the boot disk from the disk layouts itself.
    self.assertNotIn("mprov_bootdisk", content)

  def test_ships_only_the_ipv4_udhcpc_script(self):
    # mprov_boot_init.sh runs only udhcpc with default.script; the IPv6
    # default6.script was never run and is gone (#287).
    NetworkInterface.objects.create(system=self.system, name="eth0", ipaddress="10.0.0.8", bootable=True)
    content = self.get_ipxe("10.0.0.8").content.decode()
    self.assertIn("initrd /static/default.script /bin/default.script", content)
    self.assertNotIn("default6.script", content)
