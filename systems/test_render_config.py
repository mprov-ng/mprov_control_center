import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from common import render_config
from common.testing import APITestCase
from osmanagement.models import OSDistro
from scripts.models import AnsibleRole, Script, ScriptType
from systems.models import System, SystemGroup, SystemImage


class LayersMixin:
  """ A distro, an image of it, and helpers to make systems and groups. """

  def make_layers(self):
    self.user = User.objects.create(username="render-test")
    self.distro = OSDistro.objects.create(
      name="test-distro", vendor="test", version="9", baseurl="http://localhost/",
      install_kernel_cmdline="quiet", initial_mods="e1000", prov_interface="eth0", tmpfs_root_size=8,
      config_params="a: distro\nb: distro\nc: distro\nnested:\n  x: 1\n  y: 1",
    )
    self.image = SystemImage.objects.create(name="test-image", created_by=self.user, osdistro=self.distro, config_params="# inherit")

  def make_system(self, hostname, groups=(), **kwargs):
    kwargs.setdefault("systemimage", self.image)
    system = System.objects.create(hostname=hostname, created_by=self.user, **kwargs)
    system.systemgroups.add(*groups)
    return System.objects.get(pk=system.pk)


class RenderConfigOrderTests(LayersMixin, TestCase):
  """ The layers apply as OS Distro -> System Groups (by name) -> System Image
  -> System, and a System's groups are its own plus its image's. """

  def setUp(self):
    self.make_layers()

  def test_image_applies_after_groups_and_before_the_system(self):
    group = SystemGroup.objects.create(name="group", config_params="b: group\nc: group")
    self.image.config_params = "c: image\nd: image"
    self.image.save()
    system = self.make_system("order", groups=[group], config_params="d: system")
    self.assertEqual(system.config["config_params"], {
      "a": "distro", "b": "group", "c": "image", "d": "system", "nested": {"x": 1, "y": 1},
    })
    rendered = render_config(system)
    self.assertEqual(rendered["layers"], [self.distro, group, self.image, system])
    sources = {key: entry["source"] for key, entry in rendered["config_params"].items()}
    self.assertEqual(sources, {"a": self.distro, "b": group, "c": self.image, "d": system, "nested": self.distro})

  def test_image_groups_apply_to_its_systems(self):
    image_group = SystemGroup.objects.create(name="image-group", install_kernel_cmdline="console=ttyS0", config_params="b: image-group")
    self.image.systemgroups.add(image_group)
    system = self.make_system("image-group")
    self.assertEqual(system.config["install_kernel_cmdline"], "quiet console=ttyS0")
    self.assertEqual(system.config["config_params"]["b"], "image-group")

  def test_groups_from_image_and_system_merge_by_name_and_apply_once(self):
    shared = SystemGroup.objects.create(name="b-shared", initial_mods="mlx5_core")
    image_only = SystemGroup.objects.create(name="c-image", initial_mods="ixgbe")
    system_only = SystemGroup.objects.create(name="a-system", initial_mods="tg3")
    self.image.systemgroups.add(shared, image_only)
    system = self.make_system("union", groups=[shared, system_only])
    self.assertEqual(system.config["initial_mods"], "e1000,tg3,mlx5_core,ixgbe")
    self.assertEqual(render_config(system)["layers"], [self.distro, system_only, shared, image_only, self.image, system])

  def test_system_without_image_has_only_groups_and_itself(self):
    group = SystemGroup.objects.create(name="group", prov_interface="ib0")
    system = self.make_system("no-image", groups=[group], systemimage=None)
    self.assertEqual(render_config(system)["layers"], [group, system])
    self.assertEqual(system.config["prov_interface"], "ib0")

  def test_image_renders_from_its_distro_and_groups(self):
    group = SystemGroup.objects.create(name="group", config_params="b: group")
    self.image.systemgroups.add(group)
    self.image.config_params = "c: image"
    rendered = render_config(self.image)
    self.assertEqual(rendered["layers"], [self.distro, group, self.image])
    self.assertEqual({key: entry["value"] for key, entry in rendered["config_params"].items()},
                     {"a": "distro", "b": "group", "c": "image", "nested": {"x": 1, "y": 1}})

  def test_boot_field_sources(self):
    group = SystemGroup.objects.create(name="group", install_kernel_cmdline="console=ttyS0", tmpfs_root_size=16)
    system = self.make_system("sources", groups=[group], install_kernel_cmdline="=single")
    fields = render_config(system)["fields"]
    self.assertEqual(fields["install_kernel_cmdline"], {"value": "single", "sources": [system]})
    self.assertEqual(fields["tmpfs_root_size"], {"value": 16, "sources": [group]})
    self.assertEqual(fields["initial_mods"], {"value": "e1000", "sources": [self.distro]})

  def test_unsaved_system_has_empty_config(self):
    self.assertEqual(System(hostname="new", created_by=self.user).config, {})


class RenderConfigParamsTests(LayersMixin, TestCase):
  """ config_params merge by top-level key; a bad block is skipped and reported. """

  def setUp(self):
    self.make_layers()

  def test_nested_value_is_replaced_whole(self):
    system = self.make_system("nested", config_params="nested:\n  y: 2")
    self.assertEqual(system.config["config_params"]["nested"], {"y": 2})

  def test_list_of_mappings(self):
    system = self.make_system("list", config_params="- b: one\n- c: two")
    self.assertEqual(system.config["config_params"]["b"], "one")
    self.assertEqual(system.config["config_params"]["c"], "two")

  def test_invalid_yaml_is_skipped_and_reported(self):
    group = SystemGroup.objects.create(name="broken", config_params="b: [unclosed")
    system = self.make_system("invalid", groups=[group], config_params="d: system")
    self.assertEqual(system.config["config_params"]["b"], "distro")
    self.assertEqual(system.config["config_params"]["d"], "system")
    errors = render_config(system)["errors"]
    self.assertEqual(len(errors), 1)
    self.assertEqual(errors[0][0], group)
    self.assertIn("not valid YAML", errors[0][1])

  def test_non_mapping_is_skipped_and_reported(self):
    system = self.make_system("scalar", config_params="just a string")
    self.assertEqual(system.config["config_params"]["a"], "distro")
    self.assertIn("not a mapping", render_config(system)["errors"][0][1])

  def test_no_params_anywhere(self):
    self.distro.config_params = "# None"
    self.distro.save()
    system = self.make_system("none", config_params=None)
    self.assertEqual(system.config["config_params"], {})


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class RenderConfigListTests(LayersMixin, TestCase):
  """ Scripts and ansible lists are the union of every layer, by slug. """

  def setUp(self):
    self.make_layers()
    script_type = ScriptType.objects.create(name="Post Boot", slug="post-boot")
    self.distro_script = Script.objects.create(name="distro script", scriptType=script_type, content="true\n")
    self.group_script = Script.objects.create(name="group script", scriptType=script_type, content="true\n")
    self.image_script = Script.objects.create(name="image script", scriptType=script_type, content="true\n")
    self.role = AnsibleRole.objects.create(name="role", roleurl="https://example.com/roles/myrole", scriptType=script_type)

  def test_union_with_sources(self):
    self.distro.scripts.add(self.distro_script)
    group = SystemGroup.objects.create(name="group")
    group.scripts.add(self.group_script, self.distro_script)
    group.ansibleroles.add(self.role)
    self.image.scripts.add(self.image_script)
    system = self.make_system("lists", groups=[group])
    system.scripts.add(self.group_script)
    system = System.objects.get(pk=system.pk)

    self.assertEqual(system.config["scripts"], [self.distro_script.slug, self.group_script.slug, self.image_script.slug])
    self.assertEqual(system.config["ansibleroles"], [self.role.slug])
    self.assertEqual(system.config["ansibleplaybooks"], [])
    sources = {entry["item"].pk: entry["sources"] for entry in render_config(system)["scripts"]}
    self.assertEqual(sources[self.distro_script.slug], [self.distro, group])
    self.assertEqual(sources[self.group_script.slug], [group, system])
    self.assertEqual(sources[self.image_script.slug], [self.image])


class RenderConfigAPITests(LayersMixin, APITestCase):
  """ The merged config is served as `config` on /systems/. """

  def setUp(self):
    super().setUp()
    self.make_layers()

  def test_system_detail_serves_the_merged_config(self):
    group = SystemGroup.objects.create(name="group", config_params="b: group")
    system = self.make_system("api", groups=[group], install_kernel_cmdline="nomodeset")
    response = self.get_json(f"/systems/{system.pk}/")
    self.assertEqual(response.status_code, 200)
    config = response.json()["config"]
    self.assertEqual(config["install_kernel_cmdline"], "quiet nomodeset")
    self.assertEqual(config["config_params"]["b"], "group")
    self.assertEqual(config["scripts"], [])

  def test_image_detail_and_list_serve_the_merged_config(self):
    group = SystemGroup.objects.create(name="group", config_params="b: group")
    self.image.systemgroups.add(group)
    self.image.config_params = "c: image"
    self.image.save()
    detail = self.get_json(f"/systemimages/{self.image.slug}/")
    self.assertEqual(detail.status_code, 200)
    listing = self.get_json("/systemimages/")
    self.assertEqual(listing.status_code, 200)
    listed = [image for image in listing.json() if image["slug"] == self.image.slug]
    for config in (detail.json()["config"], listed[0]["config"]):
      self.assertEqual(config["config_params"], {
        "a": "distro", "b": "group", "c": "image", "nested": {"x": 1, "y": 1},
      })
      self.assertEqual(config["install_kernel_cmdline"], "quiet")
      self.assertEqual(config["scripts"], [])

  def test_image_config_is_read_only(self):
    response = self.client.patch(f"/systemimages/{self.image.slug}/", '{"config": {"x": 1}, "config_params": "d: 1"}',
                                 content_type="application/json")
    self.assertEqual(response.status_code, 200)
    self.image.refresh_from_db()
    self.assertEqual(self.image.config_params, "d: 1")
    self.assertNotIn("x", SystemImage.objects.get(pk=self.image.pk).config)

  def test_unsaved_image_has_empty_config(self):
    self.assertEqual(SystemImage(name="new", created_by=self.user).config, {})
