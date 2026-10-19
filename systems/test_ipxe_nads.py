from django.contrib.auth.models import User
from django.test import TestCase

from osmanagement.models import OSDistro
from systems.models import System, SystemImage


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

  def test_nads_boot_gets_templated_cmdline_and_rescue(self):
    self.distro.install_kernel_cmdline = "quiet img={{ nic.system.systemimage.slug }}"
    self.distro.save()
    SystemImage.objects.create(name="__nads__", created_by=self.user, osdistro=self.distro)
    content = self.client.get("/ipxe/?rescue", REMOTE_ADDR="10.0.0.99").content.decode()
    self.assertIn("quiet img=nads mprov_rescue=1", content)

  def test_nads_boot_serves_custom_ipxe(self):
    SystemImage.objects.create(name="__nads__", created_by=self.user, osdistro=self.distro,
                               customIPXE="#!ipxe\necho custom {{ nic.system.systemimage.slug }}")
    response = self.get_ipxe("10.0.0.99")
    self.assertEqual(response.content.decode(), "#!ipxe\necho custom nads")
