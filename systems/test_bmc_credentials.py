import json

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission, User
from django.test import TestCase

from jobqueue.models import Job, JobModule
from systems.models import System, SystemBMC, SystemGroup

LOGGER = "mprov.bmc"


class BMCCredentialsActionTests(TestCase):
  """ #374: the "Set BMC credentials" admin action, on systems and on system
  groups, sets the stored BMC credentials of many systems at once. """

  def setUp(self):
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(self.user)
    self.c01, self.c02, self.c03 = (System.objects.create(hostname=h, created_by=self.user) for h in ("c01", "c02", "c03"))
    self.bmc1 = SystemBMC.objects.create(system=self.c01, ipaddress="10.1.0.1", username="root", password="old1")
    self.bmc2 = SystemBMC.objects.create(system=self.c02, ipaddress="10.1.0.2", username="root", password="old2")
    # c03 has no BMC.

  def act(self, systems, url="/admin/systems/system/", action="set_bmc_credentials", **form):
    data = {"action": action, "_selected_action": [s.pk for s in systems]}
    if form:
      data.update({"apply": "1", **form})
    return self.client.post(url, data, follow=True)

  def creds(self, bmc):
    bmc.refresh_from_db()
    return bmc.username, bmc.password

  def messages(self, response):
    return [str(m) for m in response.context["messages"]]

  def test_selecting_shows_the_form_with_skipped_systems(self):
    response = self.act([self.c01, self.c02, self.c03])
    self.assertEqual(response.status_code, 200)
    self.assertTemplateUsed(response, "admin/bmc_credentials_form.html")
    self.assertEqual([s.hostname for s in response.context["updated"]], ["c01", "c02"])
    self.assertEqual([s.hostname for s in response.context["skipped"]], ["c03"])
    self.assertNotContains(response, "old1")

  def test_sets_user_and_password(self):
    with self.assertLogs(LOGGER, "INFO") as logs:
      response = self.act([self.c01, self.c02, self.c03], username="admin", password="new", confirm="new")
    self.assertEqual(self.creds(self.bmc1), ("admin", "new"))
    self.assertEqual(self.creds(self.bmc2), ("admin", "new"))
    self.assertIn("Set BMC credentials on 2 systems.", self.messages(response))
    self.assertIn("Skipped 1 systems with no BMC: c03.", self.messages(response))
    self.assertEqual(logs.output, [f"INFO:{LOGGER}:bmc: credentials set on 2 systems (c01, c02; 1 skipped with no BMC) "
                                   "by admin, user changed, password changed"])
    self.assertNotIn("new", logs.output[0].split("by admin")[0])
    self.assertIsNotNone(self.bmc1.credentials_changed)
    self.assertEqual(LogEntry.objects.filter(object_id=str(self.c01.pk), change_message="Changed BMC credentials.").count(), 1)

  def test_blank_user_keeps_each_bmcs_user(self):
    self.bmc2.username = "ADMIN"
    self.bmc2.save()
    self.act([self.c01, self.c02], password="new", confirm="new")
    self.assertEqual(self.creds(self.bmc1), ("root", "new"))
    self.assertEqual(self.creds(self.bmc2), ("ADMIN", "new"))

  def test_blank_password_keeps_each_bmcs_password(self):
    self.act([self.c01, self.c02], username="admin")
    self.assertEqual(self.creds(self.bmc1), ("admin", "old1"))
    self.assertEqual(self.creds(self.bmc2), ("admin", "old2"))

  def test_mismatched_passwords_change_nothing(self):
    response = self.act([self.c01], password="new", confirm="typo")
    self.assertTemplateUsed(response, "admin/bmc_credentials_form.html")
    self.assertContains(response, "The passwords don&#x27;t match.")
    self.assertNotContains(response, 'value="new"')
    self.assertEqual(self.creds(self.bmc1), ("root", "old1"))

  def test_nothing_to_change_is_an_error(self):
    response = self.act([self.c01], username="", password="", confirm="")
    self.assertContains(response, "Enter a new user, a new password, or both.")

  def test_no_jobs_are_queued(self):
    for slug in ("pxe-update", "dns-update", "dhcp-update"):
      JobModule.objects.get_or_create(slug=slug, defaults={"name": slug})
    Job.objects.all().delete()
    self.act([self.c01, self.c02], password="new", confirm="new")
    self.assertEqual(Job.objects.count(), 0)

  def test_group_action_covers_its_members(self):
    group = SystemGroup.objects.create(name="rack1")
    group.systems.set([self.c01, self.c03])
    response = self.act([group], url="/admin/systems/systemgroup/", password="new", confirm="new")
    self.assertEqual(self.creds(self.bmc1), ("root", "new"))
    self.assertEqual(self.creds(self.bmc2), ("root", "old2"))
    self.assertIn("Skipped 1 systems with no BMC: c03.", self.messages(response))

  def test_needs_change_systembmc_permission(self):
    staff = User.objects.create_user("staff", password="password", is_staff=True)
    staff.user_permissions.add(*Permission.objects.filter(codename__in=("view_system", "change_system")))
    self.client.force_login(staff)
    response = self.act([self.c01], password="new", confirm="new")
    self.assertIn("You don't have permission to change BMC credentials.", self.messages(response))
    self.assertEqual(self.creds(self.bmc1), ("root", "old1"))


class CredentialsChangedTests(TestCase):
  """ #374: SystemBMC.credentials_changed records when the stored username or
  password last changed, however they were changed. """

  def setUp(self):
    self.user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.system = System.objects.create(hostname="c01", created_by=self.user)

  def test_set_on_create_with_credentials_only(self):
    self.assertIsNotNone(SystemBMC.objects.create(system=self.system, ipaddress="10.1.0.1", password="x").credentials_changed)
    other = System.objects.create(hostname="c02", created_by=self.user)
    self.assertIsNone(SystemBMC.objects.create(system=other, ipaddress="10.1.0.2").credentials_changed)

  def test_changes_only_when_the_credentials_do(self):
    bmc = SystemBMC.objects.create(system=self.system, ipaddress="10.1.0.1", username="root", password="x")
    first = bmc.credentials_changed
    bmc.mac = "aa:bb:cc:dd:ee:ff"
    bmc.save()
    self.assertEqual(SystemBMC.objects.get(pk=bmc.pk).credentials_changed, first)
    bmc.password = "y"
    bmc.save()
    self.assertGreater(SystemBMC.objects.get(pk=bmc.pk).credentials_changed, first)

  def test_api_patch_of_the_mac_keeps_it(self):
    # what genNetworkInterfaces.py does with a node's BMC.
    bmc = SystemBMC.objects.create(system=self.system, ipaddress="10.1.0.1", username="root", password="x")
    first = bmc.credentials_changed
    self.client.force_login(self.user)
    response = self.client.patch(f"/systembmcs/{bmc.pk}/", json.dumps({"id": bmc.pk, "mac": "aa:bb:cc:dd:ee:ff"}),
                                 content_type="application/json")
    self.assertEqual(response.status_code, 200, response.content)
    self.assertEqual(SystemBMC.objects.get(pk=bmc.pk).credentials_changed, first)
