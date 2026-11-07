from django.contrib.auth.models import User
from django.test import TestCase

from systems.models import NetworkInterface, System, SystemBMC, SystemGroup, SystemImage, SystemModel

URL = "/admin/systems/system/"


class SystemListSearchTests(TestCase):
  """ #496: the System list searches NIC and BMC addresses as well as the
  hostname and serial, filters by image, group, model and provision, and
  loads the live search script. """

  def setUp(self):
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    self.image = SystemImage.objects.create(name="compute-img", created_by=self.user, needs_rebuild=False)
    self.model = SystemModel.objects.create(name="R650", vendor="Dell")
    self.group = SystemGroup.objects.create(name="rack1")
    self.c01 = System.objects.create(hostname="c01", created_by=self.user, serial="SER-0001",
                                     systemimage=self.image, systemmodel=self.model)
    self.c02 = System.objects.create(hostname="c02", created_by=self.user, provision=False)
    self.login = System.objects.create(hostname="login1", created_by=self.user, systemimage=self.image)
    self.c01.systemgroups.add(self.group)
    self.login.systemgroups.add(self.group)
    # two NICs on one system that both match, to check it's listed once.
    NetworkInterface.objects.create(system=self.c01, name="eth0", ipaddress="10.0.0.11", mac="aa:bb:cc:00:00:11")
    NetworkInterface.objects.create(system=self.c01, name="eth1", ipaddress="10.0.0.111", mac="aa:bb:cc:00:01:11")
    NetworkInterface.objects.create(system=self.c02, name="eth0", ipaddress="10.0.0.12", mac="aa:bb:cc:00:00:12")
    SystemBMC.objects.create(system=self.c02, ipaddress="10.1.0.12", mac="de:ad:be:ef:00:12")

  def listed(self, query):
    response = self.client.get(URL + query)
    self.assertEqual(response.status_code, 200)
    return sorted(s.hostname for s in response.context["cl"].result_list)

  def test_search_by_hostname_and_serial(self):
    self.assertEqual(self.listed("?q=login"), ["login1"])
    self.assertEqual(self.listed("?q=SER-0001"), ["c01"])

  def test_search_by_nic_ip_and_mac(self):
    self.assertEqual(self.listed("?q=10.0.0.12"), ["c02"])
    self.assertEqual(self.listed("?q=aa:bb:cc:00:00:11"), ["c01"])

  def test_search_by_bmc_ip_and_mac(self):
    self.assertEqual(self.listed("?q=10.1.0.12"), ["c02"])
    self.assertEqual(self.listed("?q=de:ad:be:ef:00:12"), ["c02"])

  def test_a_system_matching_on_two_nics_is_listed_once(self):
    self.assertEqual(self.listed("?q=10.0.0.11"), ["c01"])

  def test_filters(self):
    self.assertEqual(self.listed(f"?systemimage__slug__exact={self.image.pk}"), ["c01", "login1"])
    self.assertEqual(self.listed(f"?systemgroups__id__exact={self.group.pk}"), ["c01", "login1"])
    self.assertEqual(self.listed(f"?systemmodel__slug__exact={self.model.slug}"), ["c01"])
    self.assertEqual(self.listed("?provision__exact=0"), ["c02"])

  def test_search_and_filters_combine(self):
    self.assertEqual(self.listed(f"?q=c0&systemgroups__id__exact={self.group.pk}"), ["c01"])
    self.assertEqual(self.listed(f"?q=10.0.0&systemimage__slug__exact={self.image.pk}&provision__exact=1"), ["c01"])

  def test_page_loads_live_search_and_marks_power_icons(self):
    response = self.client.get(URL)
    self.assertContains(response, "common/admin/js/live_search.js")
    self.assertContains(response, 'id="changelist-search"')
    self.assertContains(response, f'src="/systems/{self.c01.pk}/?powerstate"')
    self.assertContains(response, "data-live-keep", count=3)
    for title in ("System Image", "System Groups", "System Model", "Provision?"):
      self.assertContains(response, f'<option value="">{title}</option>', html=True)
