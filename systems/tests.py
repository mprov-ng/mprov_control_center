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

  def test_post_without_password(self):
    other = System.objects.create(hostname="bmc-node2", created_by=self.user)
    response = self.client.post("/systembmcs/", data=f'{{"system": {other.id}, "ipaddress": "10.0.1.7"}}',
                                content_type="application/json")
    self.assertEqual(response.status_code, 201, response.content)
    self.assertEqual(SystemBMC.objects.get(system=other).ipaddress, "10.0.1.7")

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


class ImagesAPIViewTests(TestCase):
  """ /images/<pk>/ redirects to a job server hosting the image, or 404s. """

  def test_unknown_image_is_404(self):
    self.assertEqual(self.client.get("/images/nope/").status_code, 404)
    self.assertEqual(self.client.get("/images/nope.vmlinuz/").status_code, 404)


class ImagesAPIViewJobserverTests(TestCase):
  """ /images/<pk>/ picks a job server the client can resolve and reach. """

  def setUp(self):
    from jobqueue.models import JobServer
    user = User.objects.create(username="images-test")
    self.image = SystemImage.objects.create(name="compute", created_by=user, needs_rebuild=False)
    self.bad = JobServer.objects.create(name="bad", address="bad.example", one_minute_load=0.1)
    self.good = JobServer.objects.create(name="good", address="good.example", one_minute_load=0.5)
    self.ip = JobServer.objects.create(name="ip", address="10.0.0.3", one_minute_load=0.9)
    self.image.jobservers.add(self.bad, self.good, self.ip)
    patcher = mock.patch("systems.views_noauth.dns.resolver.resolve", side_effect=self.resolve)
    patcher.start()
    self.addCleanup(patcher.stop)

  @staticmethod
  def resolve(name, rdtype, search=True):
    if name == "good.example":
      return SimpleNamespace(rrset=["10.0.0.2"])
    raise Exception(f"NXDOMAIN {name}")

  def test_unresolvable_jobservers_are_skipped(self):
    from systems.views_noauth import ImagesAPIView
    self.assertEqual(ImagesAPIView().getJobserver(self.image, "10.0.0.50"), [self.good, self.ip])

  def test_no_resolvable_jobserver_is_404(self):
    from rest_framework.exceptions import NotFound
    from systems.views_noauth import ImagesAPIView
    self.image.jobservers.remove(self.good, self.ip)
    with self.assertRaises(NotFound):
      ImagesAPIView().getJobserver(self.image, "10.0.0.50")

  @mock.patch("systems.views_noauth.requests.head")
  def test_unreachable_jobserver_is_removed_from_the_image(self, head):
    head.side_effect = lambda url, timeout: SimpleNamespace(status_code=500 if "good.example" in url else 200)
    response = self.client.get("/images/compute/", REMOTE_ADDR="10.0.0.50")
    self.assertEqual(response.status_code, 302)
    self.assertEqual(response["Location"], "http://10.0.0.3:8080/images/compute/compute.img")
    # bad.example didn't resolve for this client, but it may serve others.
    self.assertEqual(sorted(js.name for js in self.image.jobservers.all()), ["bad", "ip"])


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


  def test_comment_only_field_does_not_override(self):
    self.group_b.config_params = "extra_packages:\n  - vim"
    self.group_b.save()
    for value in ("# one\n# two", "# one\n\n  # two\n"):
      system = self.make_system(f"comments-{len(value)}", groups=[self.group_b], systemimage=self.image, config_params=value)
      self.assertEqual(system.config["config_params"], "extra_packages:\n  - vim")

  def test_field_with_content_keeps_its_comments(self):
    system = self.make_system("commented", systemimage=self.image, config_params="# note\n# note 2\nfoo: 1")
    self.assertEqual(system.config["config_params"], "# note\n# note 2\nfoo: 1")

class BMCInlineTests(SimpleTestCase):
  """ The BMC inline is labelled "System BMC", with plural "System BMCs". """

  def test_labels(self):
    from systems.admin import BMCInline
    self.assertEqual(BMCInline.verbose_name, "System BMC")
    self.assertEqual(BMCInline.verbose_name_plural, "System BMCs")


class SystemBulkUpdateTests(TestCase):
  """ The "Update fields on multiple systems" admin action. """

  def setUp(self):
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    self.system = System.objects.create(hostname="bulk-node", created_by=self.user)
    self.nic = NetworkInterface.objects.create(system=self.system, name="eth0", bootable=True)

  def bulk_update(self, **data):
    data.update({"action": "bulk_update", "_selected_action": [self.system.pk], "form-post": "1"})
    response = self.client.post("/admin/systems/system/", data, follow=True)
    self.assertEqual(response.status_code, 200)
    return [str(m) for m in response.context["messages"]]

  def test_clearing_bootable_reports_only_the_clear(self):
    messages = self.bulk_update(update_set_bootable="on")
    self.nic.refresh_from_db()
    self.assertFalse(self.nic.bootable)
    self.assertIn("Bootable NIC cleared on 1 system(s).", messages)
    self.assertFalse(any(m.startswith("Bootable NIC set") for m in messages), messages)

  def test_setting_bootable(self):
    self.nic.bootable = False
    self.nic.save()
    messages = self.bulk_update(update_set_bootable="on", set_bootable="on")
    self.nic.refresh_from_db()
    self.assertTrue(self.nic.bootable)
    self.assertIn("Bootable NIC set on 1 system(s).", messages)

  def test_many_to_many_field(self):
    group = SystemGroup.objects.create(name="compute")
    self.bulk_update(update_systemgroups="on", systemgroups=[group.pk])
    self.assertEqual(list(self.system.systemgroups.all()), [group])


class MarkRebuildActionTests(TestCase):
  """ The "Mark images as needing rebuild" admin action handles every selected image and saves the new version. """

  def test_every_image_gets_a_job_and_a_new_version(self):
    from jobqueue.models import Job, JobModule, JobServer, JobStatus
    from systems.admin import mark_rebuild
    user = User.objects.create(username="rebuild-test")
    module = JobModule.objects.create(slug="image-update", name="Update Images")
    JobStatus.objects.create(pk=1, name="PENDING")
    jobserver = JobServer.objects.create(name="js1")
    images = []
    for name in ("compute", "login"):
      image = SystemImage.objects.create(name=name, created_by=user, needs_rebuild=False)
      image.jobservers.add(jobserver)
      images.append(image)
    versions = {image.pk: SystemImage.objects.get(pk=image.pk).version for image in images}
    Job.objects.all().delete()

    mark_rebuild(None, None, SystemImage.objects.all())

    for image in images:
      image = SystemImage.objects.get(pk=image.pk)
      self.assertTrue(image.needs_rebuild)
      self.assertEqual(image.version, versions[image.pk] + 1)
      self.assertEqual(list(image.jobservers.all()), [])
      self.assertEqual(Job.objects.filter(module=module, params__imageId=image.pk).count(), 1)
    self.assertEqual(SystemImage.objects.count(), 2)


class SystemRegAPIViewTests(TestCase):
  """ POST /systems/register records unknown MACs as N.A.D.S. systems. """

  packet = {"vendor": "Dell", "model": "R650", "switch": "sw1", "port": "1/1", "mac": "aa:bb:cc:dd:ee:ff"}

  def register(self, **changes):
    return self.client.post("/systems/register", {**self.packet, **changes}, content_type="application/json")

  def test_known_mac_on_a_new_port_updates_the_entry(self):
    from systems.models import NADSSystem
    self.assertEqual(self.register().status_code, 200)
    self.assertEqual(self.register(switch="sw2", port="2/7").status_code, 200)
    nads = NADSSystem.objects.get(mac=self.packet["mac"])
    self.assertEqual((nads.switch, nads.port), ("sw2", "2/7"))
    self.assertEqual(NADSSystem.objects.count(), 1)

  def test_missing_field_is_400(self):
    packet = dict(self.packet)
    del packet["vendor"]
    del packet["mac"]
    response = self.client.post("/systems/register", packet, content_type="application/json")
    self.assertEqual(response.status_code, 400)
    self.assertEqual(set(response.json()), {"vendor", "mac"})


class SystemAPIViewListTests(TestCase):
  """ GET /systems/ applies ?FIELD= filters together with ?hostname=, and keeps the base class's responses. """

  def setUp(self):
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    self.group = SystemGroup.objects.create(name="compute")
    for hostname in ("compute001", "compute002", "login001"):
      System.objects.create(hostname=hostname, created_by=self.user)
    System.objects.get(hostname="compute002").systemgroups.add(self.group)

  def get_json(self, url):
    return self.client.get(url, CONTENT_TYPE="application/json")

  def hostnames(self, response):
    self.assertEqual(response.status_code, 200)
    return sorted(s["hostname"] for s in response.json())

  def test_hostname_contains(self):
    self.assertEqual(self.hostnames(self.get_json("/systems/?hostname=compute")), ["compute001", "compute002"])

  def test_hostname_keeps_other_filters(self):
    response = self.get_json(f"/systems/?hostname=compute&systemgroups={self.group.pk}")
    self.assertEqual(self.hostnames(response), ["compute002"])

  def test_unknown_hostname_is_404(self):
    self.assertEqual(self.get_json("/systems/?hostname=nope").status_code, 404)

  def test_bad_filter_is_400(self):
    response = self.get_json("/systems/?systemgroups=not-a-number")
    self.assertEqual(response.status_code, 400)
    self.assertIn("systemgroups", response.json())

  def test_no_matches_is_an_empty_list(self):
    # libgenders in the jobserver fails its job on a 404 here.
    self.assertEqual(self.hostnames(self.get_json("/systems/?systemgroups=999")), [])

  def test_docs_page(self):
    response = self.client.get("/systems/")
    self.assertTrue(response["Content-Type"].startswith("text/html"))
    self.assertIn("<h1>/systems/</h1>", response.content.decode())


class NetworkInterfaceNetworkFilterTests(TestCase):
  """ GET /networkinterfaces/?network=SLUG reconciles NIC networks with switch port networks. """

  def setUp(self):
    from networks.models import Network, NetworkType, Switch, SwitchPort
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    net_type = NetworkType.objects.create(name="Ethernet")
    self.lan = Network.objects.create(name="Cluster LAN", net_type=net_type, subnet="172.16.0.0", netmask=16)
    self.mgmt = Network.objects.create(name="Mgmt", net_type=net_type, subnet="10.0.0.0", netmask=8)
    switch = Switch.objects.create(hostname="sw1", mgmt_ip="10.0.0.1", mgmt_mac="de:ad:be:ef:00:01", created_by=self.user)
    self.system = System.objects.create(hostname="node", created_by=self.user)
    port = lambda name, net: SwitchPort.objects.create(name=name, switch=switch, networks=net)
    self.nic("direct", self.lan, None)
    self.nic("other-port-1", self.lan, port("1", self.mgmt))
    self.nic("other-port-2", self.lan, port("2", self.mgmt))
    self.nic("port-only", None, port("3", self.lan))
    self.nic("both", self.lan, port("4", self.lan))

  def nic(self, name, network, switch_port):
    return NetworkInterface.objects.create(system=self.system, name=name, network=network, switch_port=switch_port)

  def get_json(self, url):
    return self.client.get(url, CONTENT_TYPE="application/json")

  def test_switch_port_takes_precedence(self):
    response = self.get_json("/networkinterfaces/?network=cluster-lan")
    self.assertEqual(response.status_code, 200)
    nics = {nic["name"]: nic for nic in response.json()}
    self.assertEqual(sorted(nics), ["both", "direct", "port-only"])
    self.assertEqual({nic["network"] for nic in nics.values()}, {self.lan.pk})

  def test_unknown_network_is_404(self):
    self.assertEqual(self.get_json("/networkinterfaces/?network=nope").status_code, 404)


class SystemImageAddJobserverTests(TestCase):
  """ PATCH /systemimages/<pk>/?addjs adds job servers to the image instead of replacing them. """

  def setUp(self):
    from jobqueue.models import JobServer
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    self.image = SystemImage.objects.create(name="compute", created_by=self.user, needs_rebuild=False)
    self.js1, self.js2, self.js3 = (JobServer.objects.create(name=f"js{i}") for i in range(1, 4))
    self.image.jobservers.add(self.js1)

  def addjs(self, jobservers):
    import json
    return self.client.patch(f"/systemimages/{self.image.pk}/?addjs", json.dumps({"jobservers": jobservers}),
                             content_type="application/json")

  def jobserver_ids(self):
    return sorted(self.image.jobservers.values_list("id", flat=True))

  def test_add_a_list(self):
    self.assertEqual(self.addjs([self.js2.id, self.js3.id]).status_code, 200)
    self.assertEqual(self.jobserver_ids(), [self.js1.id, self.js2.id, self.js3.id])

  def test_add_one(self):
    self.assertEqual(self.addjs(self.js2.id).status_code, 200)
    self.assertEqual(self.jobserver_ids(), [self.js1.id, self.js2.id])


class SystemPowerAPIViewQueryTests(TestCase):
  """ GET /power/<action>/ finds the BMCs to act on from the query string. """

  def setUp(self):
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    self.system = System.objects.create(hostname="power-node", created_by=self.user)
    self.bmc = SystemBMC.objects.create(system=self.system, ipaddress="10.0.2.5", username="admin", password="pw")
    patcher = mock.patch.object(SystemPowerAPIView, "_doPowerCmd", return_value={"status": 200})
    self.power = patcher.start()
    self.addCleanup(patcher.stop)

  def get_json(self, url):
    return self.client.get(url, CONTENT_TYPE="application/json")

  def test_by_id(self):
    response = self.get_json(f"/power/status/?id={self.system.id}")
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json(), {str(self.bmc): {"status": 200}})

  def test_unknown_id_is_404(self):
    self.assertEqual(self.get_json("/power/status/?id=999").status_code, 404)
    self.power.assert_not_called()

  def test_bad_id_is_400(self):
    self.assertEqual(self.get_json("/power/status/?id=abc").status_code, 400)
