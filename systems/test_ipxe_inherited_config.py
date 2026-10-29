from django.contrib.auth.models import User
from django.test import TestCase

from osmanagement.models import OSDistro
from systems.models import NetworkInterface, System, SystemGroup, SystemImage


class IPXEInheritedConfigTests(TestCase):
  """ /ipxe/ boots with the merged config (System.config), so system group,
  image group and system values for the cmdline, modules and tmpfs size reach
  the node, not just the distro's. """

  def setUp(self):
    self.user = User.objects.create(username="ipxe-config-test")
    self.distro = OSDistro.objects.create(
      name="test-distro", vendor="test", version="9", baseurl="http://localhost/",
      install_kernel_cmdline="quiet", initial_mods="e1000", prov_interface="eth0", tmpfs_root_size=8,
    )
    self.image = SystemImage.objects.create(name="test-image", created_by=self.user, osdistro=self.distro)

  def boot(self, ip="10.0.0.8", groups=(), query="", **kwargs):
    system = System.objects.create(hostname="node01", created_by=self.user, systemimage=self.image, **kwargs)
    system.systemgroups.add(*groups)
    NetworkInterface.objects.create(system=system, name="eth0", ipaddress=ip, bootable=True)
    return self.client.get(f"/ipxe/{query}", REMOTE_ADDR=ip).content.decode()

  def test_distro_only(self):
    content = self.boot()
    self.assertIn("mprov_initial_mods=e1000\n", content)
    self.assertIn("mprov_tmpfs_size=8G", content)
    self.assertIn("${kernel-cmdline} quiet mprov_rescue=0\n", content)

  def test_group_and_system_values_reach_the_node(self):
    group = SystemGroup.objects.create(name="gpu", install_kernel_cmdline="console=ttyS0", initial_mods="mlx5_core", tmpfs_root_size=16)
    content = self.boot(groups=[group], install_kernel_cmdline="nomodeset", initial_mods="ixgbe")
    self.assertIn("mprov_initial_mods=e1000,mlx5_core,ixgbe\n", content)
    self.assertIn("mprov_tmpfs_size=16G", content)
    self.assertIn("${kernel-cmdline} quiet console=ttyS0 nomodeset mprov_rescue=0\n", content)

  def test_image_groups_apply(self):
    group = SystemGroup.objects.create(name="image-group", initial_mods="=virtio_net")
    self.image.systemgroups.add(group)
    self.assertIn("mprov_initial_mods=virtio_net\n", self.boot())

  def test_system_overwrite_and_rescue(self):
    content = self.boot(install_kernel_cmdline="=single", tmpfs_root_size=32, query="?rescue")
    self.assertIn("mprov_tmpfs_size=32G", content)
    self.assertIn("${kernel-cmdline} single mprov_rescue=1\n", content)

  def test_merged_cmdline_is_templated(self):
    group = SystemGroup.objects.create(name="named", install_kernel_cmdline="host={{ nic.system.hostname }}")
    self.assertIn("${kernel-cmdline} quiet host=node01 mprov_rescue=0\n", self.boot(groups=[group]))

  def test_image_without_distro_gets_the_distro_defaults(self):
    self.image.osdistro = None
    self.image.save()
    content = self.boot()
    self.assertIn(f"mprov_initial_mods={OSDistro().initial_mods}\n", content)
    self.assertIn(f"mprov_tmpfs_size={OSDistro().tmpfs_root_size}G", content)

  def test_nads_boot_uses_the_nads_image_merge(self):
    nads = SystemImage.objects.create(name="__nads__", created_by=self.user, osdistro=self.distro)
    group = SystemGroup.objects.create(name="nads-group", initial_mods="tg3", install_kernel_cmdline="nads=1")
    nads.systemgroups.add(group)
    content = self.client.get("/ipxe/", REMOTE_ADDR="10.0.0.99").content.decode()
    self.assertIn("mprov_image_url=", content)
    self.assertIn("/images/nads\n", content)
    self.assertIn("mprov_initial_mods=e1000,tg3\n", content)
    self.assertIn("${kernel-cmdline} quiet nads=1 mprov_rescue=0\n", content)

  def test_not_provisioning_still_local_boots(self):
    content = self.boot(provision=False)
    self.assertIn("Attempting local boot", content)
    self.assertNotIn("mprov_initial_mods", content)
