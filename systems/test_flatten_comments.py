from django.contrib.auth.models import User
from django.test import TestCase

from osmanagement.models import OSDistro
from systems.models import System, SystemGroup, SystemImage


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

  def test_comment_only_field_does_not_override(self):
    self.group_b.config_params = "extra_packages:\n  - vim"
    self.group_b.save()
    for value in ("# one\n# two", "# one\n\n  # two\n"):
      system = self.make_system(f"comments-{len(value)}", groups=[self.group_b], systemimage=self.image, config_params=value)
      self.assertEqual(system.config["config_params"], "extra_packages:\n  - vim")

  def test_field_with_content_keeps_its_comments(self):
    system = self.make_system("commented", systemimage=self.image, config_params="# note\n# note 2\nfoo: 1")
    self.assertEqual(system.config["config_params"], "# note\n# note 2\nfoo: 1")
