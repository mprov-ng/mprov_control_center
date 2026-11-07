from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission, User
from django.test import SimpleTestCase, TestCase

from jobqueue.models import Job, JobModule, JobStatus
from networks.models import Network, NetworkType, Switch, SwitchPort
from systems.models import NADSSystem, NetworkInterface, System, SystemBMC, SystemGroup, SystemImage, SystemModel
from systems.range_wizard import address_range, expand_range

URL = "/admin/systems/system/add-range/"


class ExpandRangeTests(SimpleTestCase):
  """ #38: hostname and switch port patterns. """

  def test_padding_follows_the_start(self):
    self.assertEqual(expand_range("c[001-003]"), ["c001", "c002", "c003"])
    self.assertEqual(expand_range("c[1-3]"), ["c1", "c2", "c3"])
    self.assertEqual(expand_range("c[8-10]"), ["c8", "c9", "c10"])

  def test_prefix_and_suffix(self):
    self.assertEqual(expand_range("gpu[01-02].cluster"), ["gpu01.cluster", "gpu02.cluster"])
    self.assertEqual(expand_range("1/[1-2]"), ["1/1", "1/2"])

  def test_bad_patterns(self):
    for pattern in ("c001", "c[1-2]-[3-4]", "c[5-1]", "c[a-b]", "c[1-1001]"):
      with self.assertRaises(ValueError, msg=pattern):
        expand_range(pattern)


class AddressRangeTests(TestCase):
  def test_counts_up_inside_the_network(self):
    net = Network(name="LAN", subnet="10.0.0.0", netmask=24)
    self.assertEqual(address_range("10.0.0.10", 3, net), ["10.0.0.10", "10.0.0.11", "10.0.0.12"])

  def test_running_past_the_network(self):
    net = Network(name="LAN", subnet="10.0.0.0", netmask=24)
    with self.assertRaises(ValueError):
      address_range("10.0.0.250", 10, net)   # would reach 10.0.0.255, the broadcast address

  def test_without_a_network(self):
    self.assertEqual(address_range("10.0.0.254", 3, None), ["10.0.0.254", "10.0.0.255", "10.0.1.0"])


class RangeWizardTests(TestCase):
  """ #38: the "Add systems from a range" admin wizard. """

  def setUp(self):
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    net_type = NetworkType.objects.create(name="Ethernet")
    self.lan = Network.objects.create(name="Cluster LAN", net_type=net_type, subnet="10.0.0.0", netmask=24)
    self.mgmt = Network.objects.create(name="Mgmt", net_type=net_type, subnet="10.1.0.0", netmask=24)
    self.switch = Switch.objects.create(hostname="sw1", mgmt_ip="10.1.0.250", mgmt_mac="de:ad:be:ef:00:01", created_by=self.user)
    for n in range(1, 5):
      SwitchPort.objects.create(name=f"1/{n}", switch=self.switch, networks=self.lan)
    self.model = SystemModel.objects.create(name="R650", vendor="Dell")
    self.group = SystemGroup.objects.create(name="compute")

  def post(self, button="create", **form):
    data = {"hostnames": "c[01-03]", "nic_name": "eth0", "nic_bootable": "on", button: "1"}
    data.update(form)
    return self.client.post(URL, data)

  def hostnames(self):
    return list(System.objects.order_by("hostname").values_list("hostname", flat=True))

  def test_form_and_list_button(self):
    response = self.client.get(URL)
    self.assertEqual(response.status_code, 200)
    self.assertContains(response, f'<option value="{self.switch.pk}">sw1</option>', html=True)
    self.assertContains(self.client.get("/admin/systems/system/"), URL)

  def test_preview_creates_nothing(self):
    response = self.post("preview", nic_network=self.lan.pk, nic_start_ip="10.0.0.11")
    self.assertEqual(response.status_code, 200)
    self.assertContains(response, "Preview: 3 systems")
    self.assertContains(response, "10.0.0.13")
    self.assertContains(response, "Create 3 systems")
    self.assertEqual(System.objects.count(), 0)

  def test_creates_systems_nics_ports_and_bmcs(self):
    response = self.post(
      systemmodel=self.model.slug, systemgroups=[self.group.pk], stateful="yes",
      nic_network=self.lan.pk, nic_start_ip="10.0.0.11",
      macs="AA:BB:CC:00:00:01\naa-bb-cc-00-00-02\naa:bb:cc:00:00:03\n",
      switch=self.switch.pk, port_pattern="1/[1-3]",
      bmc_network=self.mgmt.pk, bmc_start_ip="10.1.0.11", bmc_username="root", bmc_password="secret")
    self.assertEqual(response.status_code, 302, response.content[:2000])
    self.assertIn("q=c", response["Location"])
    self.assertEqual(self.hostnames(), ["c01", "c02", "c03"])
    c02 = System.objects.get(hostname="c02")
    self.assertEqual((c02.systemmodel, c02.stateful, list(c02.systemgroups.all())), (self.model, True, [self.group]))
    nic = NetworkInterface.objects.get(system=c02)
    self.assertEqual((nic.name, nic.ipaddress, nic.mac, str(nic.switch_port), nic.network, nic.bootable, nic.hostname),
                     ("eth0", "10.0.0.12", "aa:bb:cc:00:00:02", "sw1/1/2", self.lan, True, "c02"))
    bmc = SystemBMC.objects.get(system=c02)
    self.assertEqual((bmc.ipaddress, bmc.username, bmc.password, bmc.network), ("10.1.0.12", "root", "secret", self.mgmt))
    self.assertEqual(LogEntry.objects.filter(change_message__contains="range wizard").count(), 3)

  def test_without_nic_fields_no_nic(self):
    self.post()
    self.assertEqual(self.hostnames(), ["c01", "c02", "c03"])
    self.assertEqual(NetworkInterface.objects.count(), 0)
    self.assertEqual(SystemBMC.objects.count(), 0)

  def test_copy_from_with_overrides(self):
    distro_image = SystemImage.objects.create(name="img", created_by=self.user)
    other_image = SystemImage.objects.create(name="img2", created_by=self.user)
    template = System.objects.create(hostname="tmpl", created_by=self.user, systemimage=distro_image,
                                     systemmodel=self.model, stateful=True, initial_mods="mlx5", serial="SER1")
    template.systemgroups.set([self.group])
    NetworkInterface.objects.create(system=template, name="eth0", ipaddress="10.0.0.200")
    self.post(hostnames="n[1-2]", copy_from=template.pk, systemimage=other_image.pk, stateful="no")
    n1 = System.objects.get(hostname="n1")
    self.assertEqual((n1.systemimage, n1.systemmodel, n1.stateful, n1.initial_mods, n1.serial),
                     (other_image, self.model, False, "mlx5", None))
    self.assertEqual(list(n1.systemgroups.all()), [self.group])
    self.assertEqual(NetworkInterface.objects.filter(system=n1).count(), 0)

  def test_problems_block_creation(self):
    System.objects.create(hostname="c02", created_by=self.user)
    other = System.objects.create(hostname="x", created_by=self.user)
    NetworkInterface.objects.create(system=other, name="eth0", ipaddress="10.0.0.13", mac="aa:bb:cc:00:00:01",
                                    switch_port=SwitchPort.objects.get(name="1/1"))
    response = self.post(nic_network=self.lan.pk, nic_start_ip="10.0.0.11",
                         macs="aa:bb:cc:00:00:01\naa:bb:cc:00:00:09\nnot-a-mac", switch=self.switch.pk, port_pattern="1/[1-3]")
    self.assertEqual(response.status_code, 200)
    for problem in ("A system with this hostname already exists.", "IP address 10.0.0.13 is already in use.",
                    "MAC aa:bb:cc:00:00:01 is already on a NIC.", "not:a:mac isn&#x27;t a MAC address.",
                    "Switch port sw1/1/1 is already used by a NIC."):
      self.assertContains(response, problem)
    self.assertNotContains(response, "Create 3 systems")
    self.assertEqual(self.hostnames(), ["c02", "x"])

  def test_range_level_problems(self):
    response = self.post(nic_network=self.lan.pk, nic_start_ip="10.0.0.253", macs="aa:bb:cc:00:00:01",
                         switch=self.switch.pk, port_pattern="1/[1-9]")
    for problem in ("don&#x27;t fit", "1 MAC addresses for 3 systems", "9 switch ports for 3 systems"):
      self.assertContains(response, problem)
    response = self.post(switch=self.switch.pk, port_pattern="1/[3-5]")
    self.assertContains(response, "There&#x27;s no port 1/5 on sw1.")
    self.assertEqual(System.objects.count(), 0)

  def test_form_errors(self):
    response = self.post(hostnames="c[3-1]", port_pattern="1/[1-3]")
    self.assertContains(response, "The range starts after it ends")
    response = self.post(port_pattern="1/[1-3]")
    self.assertContains(response, "Choose the switch the ports are on.")
    response = self.post(bmc_username="root")
    self.assertContains(response, "Enter the first BMC IP address")

  def test_bmc_password_kept_from_preview_and_not_echoed(self):
    form = dict(bmc_start_ip="10.1.0.11", bmc_network=self.mgmt.pk, bmc_password="secret")
    response = self.post("preview", **form)
    self.assertNotContains(response, "secret")
    self.assertContains(response, "The password from the preview is kept")
    del form["bmc_password"]
    self.assertEqual(self.post(**form).status_code, 302)
    self.assertEqual(SystemBMC.objects.get(system__hostname="c01").password, "secret")
    self.assertNotIn("range_wizard_bmc_password", self.client.session)

  def test_needs_add_permission(self):
    staff = User.objects.create_user("staff", password="password", is_staff=True)
    staff.user_permissions.add(Permission.objects.get(codename="view_system"))
    self.client.force_login(staff)
    self.assertEqual(self.client.get(URL).status_code, 403)
    self.assertNotContains(self.client.get("/admin/systems/system/"), URL)

  def test_jobs_are_collapsed(self):
    for pk, name in ((1, "PENDING"), (2, "RUNNING"), (3, "COMPLETE")):
      JobStatus.objects.get_or_create(pk=pk, defaults={"name": name})
    for slug in ("pxe-update", "dns-update", "dhcp-update", "libgenders"):
      JobModule.objects.get_or_create(slug=slug, defaults={"name": slug})
    Job.objects.all().delete()
    self.post(hostnames="c[001-020]", nic_network=self.lan.pk, nic_start_ip="10.0.0.11")
    self.assertEqual(System.objects.count(), 20)
    self.assertLessEqual(Job.objects.count(), 4)

  def test_nads_fills_in_a_wizard_nic(self):
    # the NADS workflow: a NIC on a switch port with no MAC gets the MAC of the
    # node that boots N.A.D.S. on that port.
    self.post(hostnames="c[1-2]", systemmodel=self.model.slug, switch=self.switch.pk, port_pattern="1/[1-2]")
    packet = {"vendor": "Dell", "model": "R650", "switch": "sw1", "port": "1/2", "mac": "aa:bb:cc:dd:ee:02"}
    self.assertEqual(self.client.post("/systems/register", packet, content_type="application/json").status_code, 200)
    self.assertEqual(NetworkInterface.objects.get(system__hostname="c2").mac, "aa:bb:cc:dd:ee:02")
    self.assertFalse(NADSSystem.objects.exists())
