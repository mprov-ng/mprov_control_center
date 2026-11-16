from jobqueue.models import Job, JobModule, JobStatus
from networks.testing import NetworkTestCase

PENDING, RUNNING = 1, 2
DNSMASQ = ("pxe-update", "dns-update", "dhcp-update")


class ForceDNSUpdateTests(NetworkTestCase):
  """ "Force DNS update" on a network's change page, and as a bulk action on
  the networks list, queues the DNS, DHCP and PXE jobs even when nothing they
  build from changed (#569). """

  def setUp(self):
    super().setUp()
    for pk, name in ((PENDING, "PENDING"), (RUNNING, "RUNNING")):
      JobStatus.objects.get_or_create(pk=pk, defaults={"name": name})
    self.modules = [JobModule.objects.get_or_create(slug=slug, defaults={"name": slug})[0] for slug in DNSMASQ]
    # every field the dnsmasq jobs read is set, so a save that changes
    # nothing really changes nothing: an empty IP field posts '' where the
    # database has NULL, which counts as a change.
    self.ips = {"gateway": "172.16.0.1", "nameserver1": "172.16.0.2", "dhcpstart": "172.16.1.0", "dhcpend": "172.16.1.255"}
    for name, value in self.ips.items():
      setattr(self.lan, name, value)
    self.lan.save()
    Job.objects.all().delete()

  def change_url(self, network):
    return f"/admin/networks/network/{network.pk}/change/"

  def form_data(self, **extra):
    data = {"name": self.lan.name, "net_type": self.net_type.pk, "vlan": self.lan.vlan, "subnet": self.lan.subnet,
            "netmask": self.lan.netmask, "domain": "", **self.ips}
    data.update(extra)
    return data

  def pending(self):
    return sorted(Job.objects.filter(status_id=PENDING).values_list("module__slug", flat=True))

  def messages(self, response):
    return [(m.level_tag, str(m)) for m in response.context["messages"]]

  def test_button_on_change_page_only(self):
    self.assertContains(self.client.get(self.change_url(self.lan)), 'name="_force_dns_update"')
    self.assertNotContains(self.client.get("/admin/networks/network/add/"), 'name="_force_dns_update"')

  def test_plain_save_without_changes_queues_nothing(self):
    self.client.post(self.change_url(self.lan), self.form_data(_save="Save"))
    self.assertEqual(self.pending(), [])

  def test_button_queues_the_jobs_without_any_change(self):
    response = self.client.post(self.change_url(self.lan), self.form_data(_force_dns_update="Force DNS update"))
    self.assertRedirects(response, self.change_url(self.lan), fetch_redirect_response=False)
    self.assertEqual(self.pending(), sorted(DNSMASQ))
    response = self.client.get(response["Location"])
    self.assertIn(("success", "Queued a DNS, DHCP and PXE update for Cluster LAN. "
                              "The job servers rebuild the config for every network."), self.messages(response))

  def test_button_saves_the_form_too(self):
    self.client.post(self.change_url(self.lan), self.form_data(name="Cluster LAN 2", _force_dns_update="Force DNS update"))
    self.lan.refresh_from_db()
    self.assertEqual(self.lan.name, "Cluster LAN 2")
    self.assertEqual(self.pending(), sorted(DNSMASQ))

  def test_bulk_action_queues_each_job_once(self):
    response = self.client.post("/admin/networks/network/", {
      "action": "force_dns_update", "_selected_action": [self.lan.pk, self.mgmt.pk]}, follow=True)
    self.assertEqual(self.pending(), sorted(DNSMASQ))
    self.assertIn(("success", "Queued a DNS, DHCP and PXE update for Cluster LAN, Mgmt. "
                              "The job servers rebuild the config for every network."), self.messages(response))

  def test_an_already_pending_job_is_not_duplicated(self):
    self.client.post(self.change_url(self.lan), self.form_data(_force_dns_update="Force DNS update"))
    self.client.post(self.change_url(self.lan), self.form_data(_force_dns_update="Force DNS update"))
    self.assertEqual(self.pending(), sorted(DNSMASQ))

  def test_a_running_job_gets_a_pending_one_after_it(self):
    Job.objects.create(name=self.modules[1].name, module=self.modules[1], status_id=RUNNING)
    self.client.post(self.change_url(self.lan), self.form_data(_force_dns_update="Force DNS update"))
    self.assertEqual(self.pending(), sorted(DNSMASQ))
    self.assertEqual(Job.objects.filter(module=self.modules[1], status_id=RUNNING).count(), 1)

  def test_no_job_modules_is_a_warning(self):
    JobModule.objects.filter(slug__in=DNSMASQ).delete()
    response = self.client.post(self.change_url(self.lan), self.form_data(_force_dns_update="Force DNS update"),
                                follow=True)
    self.assertEqual(Job.objects.count(), 0)
    self.assertIn(("warning", "No DNS update was queued for Cluster LAN: there's no DNS, DHCP or PXE job module."),
                  self.messages(response))
