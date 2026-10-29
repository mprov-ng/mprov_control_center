import tempfile

from django.test import override_settings

from common.testing import APITestCase
from osmanagement.models import OSDistro
from scripts.models import Script, ScriptType
from systems.models import System, SystemGroup, SystemImage


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class RenderedConfigTabTests(APITestCase):
  """ System and system image change pages have a Rendered Config tab showing
  the merged config and where each value came from (#269, #154). """

  def setUp(self):
    super().setUp()
    self.distro = OSDistro.objects.create(
      name="test-distro", vendor="test", version="9", baseurl="http://localhost/",
      install_kernel_cmdline="quiet", initial_mods="e1000", prov_interface="eth0", tmpfs_root_size=8,
      config_params="rootpw: distro\nextra_packages:\n  - vim",
    )
    self.image = SystemImage.objects.create(name="compute", created_by=self.user, osdistro=self.distro, config_params="# inherit")
    self.group = SystemGroup.objects.create(name="gpu", install_kernel_cmdline="console=ttyS0", config_params="gpus: 4")
    script_type = ScriptType.objects.create(name="Post Boot", slug="post-boot")
    self.script = Script.objects.create(name="enable gpus", scriptType=script_type, content="true\n")
    self.group.scripts.add(self.script)
    self.system = System.objects.create(hostname="node01", created_by=self.user, systemimage=self.image,
                                        install_kernel_cmdline="nomodeset", config_params="note: '<b>hi</b>'")
    self.system.systemgroups.add(self.group)

  def page(self, url):
    response = self.client.get(url)
    self.assertEqual(response.status_code, 200)
    return response.content.decode()

  def test_system_tab_shows_values_and_their_sources(self):
    html = self.page(f"/admin/systems/system/{self.system.pk}/change/")
    self.assertIn('href="#rendered-config-tab"', html)
    distro = f'<a href="/admin/osmanagement/osdistro/{self.distro.pk}/change/">OS Distribution: test-distro</a>'
    group = f'<a href="/admin/systems/systemgroup/{self.group.pk}/change/">System Group: gpu</a>'
    image = f'<a href="/admin/systems/systemimage/{self.image.pk}/change/">System Image: compute</a>'
    self.assertIn(f"{distro} &rarr; {group} &rarr; {image} &rarr; this system", html)
    self.assertInHTML(f"<tr><td>Install kernel command line</td><td><code>quiet console=ttyS0 nomodeset</code></td>"
                      f"<td>{distro}, {group}, this system</td></tr>", html)
    self.assertInHTML(f"<tr><td><code>gpus</code></td><td><pre>4</pre></td><td>{group}</td></tr>", html)
    self.assertInHTML(f"<tr><td><code>extra_packages</code></td><td><pre>- vim</pre></td><td>{distro}</td></tr>", html)
    self.assertInHTML(f'<tr><td><a href="/admin/scripts/script/{self.script.pk}/change/">enable gpus</a></td>'
                      f"<td>Post Boot</td><td>{group}</td></tr>", html)
    self.assertIn("config</code> field in the mPCC API", html)
    self.assertIn("&quot;gpus&quot;: 4", html)

  def test_values_are_escaped(self):
    html = self.page(f"/admin/systems/system/{self.system.pk}/change/")
    self.assertNotIn("<b>hi</b>", html)
    self.assertIn("&lt;b&gt;hi&lt;/b&gt;", html)

  def test_bad_params_are_reported(self):
    self.group.config_params = "gpus: [4"
    self.group.save()
    html = self.page(f"/admin/systems/system/{self.system.pk}/change/")
    self.assertIn('<div class="alert alert-warning">', html)
    self.assertIn("Configuration Parameters skipped, not valid YAML", html)

  def test_image_tab(self):
    self.image.systemgroups.add(self.group)
    html = self.page(f"/admin/systems/systemimage/{self.image.pk}/change/")
    self.assertIn('href="#rendered-config-tab"', html)
    self.assertIn("&rarr; this system image", html)
    self.assertNotIn("field in the mPCC API", html)

  def test_add_pages_have_no_tab(self):
    for url in ("/admin/systems/system/add/", "/admin/systems/systemimage/add/"):
      self.assertNotIn("rendered-config-tab", self.page(url))

  def test_rendered_config_is_not_a_form_input(self):
    html = self.page(f"/admin/systems/system/{self.system.pk}/change/")
    self.assertNotIn('name="rendered_config"', html)
