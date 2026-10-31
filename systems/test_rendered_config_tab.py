import re
import tempfile

from django.test import override_settings

from common.rendered_config import LIST_LABELS
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


  def tab(self, url):
    """ The tab's own markup, from its root <div> to the </div> closing it. """
    html = self.page(url)
    start = html.index('<div class="rendered-config">')
    depth = 0
    for match in re.finditer(r"<div\b|</div>", html[start:]):
      depth += 1 if match.group() != "</div>" else -1
      if depth == 0:
        return html[start:start + match.end()]
    self.fail("the Rendered Config tab's <div> never closes")

  def assertCards(self, url):
    """ Each section is a card inside the tab, empty ones too (#423). """
    html = self.tab(url)
    titles = re.findall(r'<div class="card card-secondary card-outline"><div class="card-header">'
                        r'<h3 class="card-title">([^<]*)</h3></div>', html)
    self.assertEqual(titles, ["How this is merged", "Boot options", "Configuration Parameters", *LIST_LABELS.values(),
                              "Merged result"])
    return html

  def test_system_tab_sections_are_cards(self):
    html = self.assertCards(f"/admin/systems/system/{self.system.pk}/change/")
    # the inheritance line stays above the cards; an empty list still says so.
    self.assertLess(html.index("Inherits from"), html.index('class="card '))
    self.assertIn("None.", html)

  def test_image_tab_sections_are_cards(self):
    self.assertCards(f"/admin/systems/systemimage/{self.image.pk}/change/")

  def test_empty_sections_are_cards_too(self):
    bare = System.objects.create(hostname="bare", created_by=self.user)
    self.assertIn("None set.", self.assertCards(f"/admin/systems/system/{bare.pk}/change/"))
