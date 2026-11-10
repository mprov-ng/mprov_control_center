from common.testing import APITestCase
from jobqueue.models import DNSMASQ_JOBS, Job, JobModule, JobStatus
from networks.models import Network, NetworkType
from systems.models import NetworkInterface, System, SystemBMC

PENDING = 1


class DnsmasqTriggerTests(APITestCase):
  """ A system, NIC, BMC or network save queues the dnsmasq plugin's jobs only
  if it's new or changes a field the plugin builds its config from (#546). """

  def setUp(self):
    super().setUp()
    JobStatus.objects.get_or_create(pk=PENDING, defaults={"name": "PENDING"})
    for slug in DNSMASQ_JOBS:
      JobModule.objects.get_or_create(slug=slug, defaults={"name": slug})
    net_type = NetworkType.objects.create(name="Ethernet")
    self.lan = Network.objects.create(name="LAN", net_type=net_type, subnet="10.0.0.0", netmask=16)
    self.other = Network.objects.create(name="Other", net_type=net_type, subnet="10.1.0.0", netmask=16)
    self.system = System.objects.create(hostname="c01", created_by=self.user)
    self.nic = NetworkInterface.objects.create(system=self.system, name="eth0", ipaddress="10.0.0.11",
                                               mac="aa:bb:cc:dd:ee:01", network=self.lan)
    self.bmc = SystemBMC.objects.create(system=self.system, ipaddress="10.0.1.11", mac="aa:bb:cc:dd:ee:02",
                                        username="root", password="old", network=self.lan)
    self.clear()

  def clear(self):
    Job.objects.all().delete()

  def queued(self):
    return sorted(Job.objects.filter(status_id=PENDING).values_list("module_id", flat=True))

  def assertQueued(self, what):
    self.assertEqual(self.queued(), sorted(DNSMASQ_JOBS), what)
    self.clear()

  def assertNotQueued(self, what):
    self.assertEqual(self.queued(), [], what)

  def change(self, obj, **values):
    obj.refresh_from_db()
    for field, value in values.items():
      setattr(obj, field, value)
    obj.save()

  def test_new_objects_queue_the_jobs(self):
    self.system = System.objects.create(hostname="c02", created_by=self.user)
    self.assertQueued("new system")
    NetworkInterface.objects.create(system=self.system, name="eth0")
    self.assertQueued("new NIC")
    SystemBMC.objects.create(system=self.system, ipaddress="10.0.1.12")
    self.assertQueued("new BMC")
    Network.objects.create(name="New", net_type=self.lan.net_type, subnet="10.2.0.0", netmask=16)
    self.assertQueued("new network")

  def test_unchanged_saves_queue_nothing(self):
    for obj in (self.system, self.nic, self.bmc, self.lan):
      self.change(obj)
      self.assertNotQueued(type(obj).__name__)

  def test_system(self):
    for field, value in (("provision", False), ("stateful", True), ("serial", "ABC123"),
                         ("config_params", "a: 1"), ("install_kernel_cmdline", "quiet")):
      self.change(self.system, **{field: value})
      self.assertNotQueued(field)
    self.change(self.system, hostname="c99")
    self.assertQueued("hostname")

  def test_nic(self):
    for field, value in (("bootable", True), ("mtu", 9000), ("isgateway", False), ("name", "eth1")):
      self.change(self.nic, **{field: value})
      self.assertNotQueued(field)
    other = System.objects.create(hostname="c02", created_by=self.user)
    self.clear()
    for field, value in (("hostaliases", "head"), ("ipaddress", "10.0.0.12"), ("ipv6ll", "fe80::1"),
                         ("mac", "aa:bb:cc:dd:ee:03"), ("network", self.other), ("system", other)):
      self.change(self.nic, **{field: value})
      self.assertQueued(field)

  def test_bmc(self):
    for field, value in (("username", "admin"), ("password", "new"), ("vlan", 5), ("ipv6ll", "fe80::2")):
      self.change(self.bmc, **{field: value})
      self.assertNotQueued(field)
    other = System.objects.create(hostname="c02", created_by=self.user)
    self.clear()
    for field, value in (("ipaddress", "10.0.1.12"), ("mac", "aa:bb:cc:dd:ee:04"), ("network", self.other),
                         ("system", other)):
      self.change(self.bmc, **{field: value})
      self.assertQueued(field)

  def test_network(self):
    for field, value in (("name", "Renamed"), ("vlan", 7), ("isbootable", True)):
      self.change(self.lan, **{field: value})
      self.assertNotQueued(field)
    for field, value in (("slug", "lan2"), ("subnet", "10.4.0.0"), ("netmask", 24), ("gateway", "10.4.0.1"),
                         ("nameserver1", "10.4.0.2"), ("domain", "cluster"), ("isdhcp", True),
                         ("managedns", True), ("dhcpstart", "10.4.0.100"), ("dhcpend", "10.4.0.200")):
      self.change(self.lan, **{field: value})
      self.assertQueued(field)

  def test_update_fields_counts_only_the_saved_fields(self):
    self.nic.refresh_from_db()
    self.nic.mac = "aa:bb:cc:dd:ee:05"
    self.nic.bootable = True
    self.nic.save(update_fields=["bootable"])
    self.assertNotQueued("only bootable saved")
    self.nic.save(update_fields=["mac"])
    self.assertQueued("mac saved")
    self.bmc.network = self.other
    self.bmc.save(update_fields=["network_id"])
    self.assertQueued("saved by attname")

  def test_a_system_hostname_change_reaches_its_nics(self):
    # the plugin reads the NICs' copies of the hostname, which System.save()
    # updates without a NIC save; the system's own save queues the jobs.
    self.change(self.system, hostname="c42")
    self.assertQueued("hostname")
    self.nic.refresh_from_db()
    self.assertEqual(self.nic.hostname, "c42")

  def test_no_job_modules_no_jobs(self):
    JobModule.objects.filter(slug__in=DNSMASQ_JOBS).delete()
    self.change(self.nic, mac="aa:bb:cc:dd:ee:06")
    self.assertNotQueued("no modules")
