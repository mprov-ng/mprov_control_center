import subprocess
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from systems import bootdev
from systems.models import NetworkInterface, SystemBMC
from systems.test_provision import ProvisionTestCase

FAILED = {"details": "Setting the boot device to PXE failed (ipmitool exited 1: Error: Unable to establish IPMI v2 / RMCP+ session).  It was not reset.",
          "status": 502, "chassis_status": "unknown"}


class SetPXEBootdevTests(SimpleTestCase):
  """ Issue #311: systems/bootdev.py checks what ipmitool says. """

  bmc = SimpleNamespace(username="admin", ipaddress="10.0.2.30", password="s3cret")

  def run_bootdev(self, efi=False, **result):
    run = mock.patch("systems.bootdev.subprocess.run", **result)
    with run as fake, mock.patch("builtins.print"):
      return bootdev.set_pxe_bootdev(self.bmc, efi=efi), fake

  def test_success(self):
    failed, run = self.run_bootdev(return_value=SimpleNamespace(returncode=0, stderr=""))
    self.assertIsNone(failed)
    args, kwargs = run.call_args
    self.assertEqual(args[0][-3:], ["chassis", "bootdev", "pxe"])
    self.assertEqual(kwargs["env"]["IPMI_PASSWORD"], "s3cret")
    self.assertNotIn("s3cret", " ".join(args[0]))
    self.assertEqual(kwargs["timeout"], bootdev.BOOTDEV_TIMEOUT)
    self.assertTrue(kwargs["capture_output"])

  def test_efi(self):
    _, run = self.run_bootdev(efi=True, return_value=SimpleNamespace(returncode=0, stderr=""))
    self.assertEqual(run.call_args.args[0][-4:], ["chassis", "bootdev", "pxe", "options=efiboot"])

  def test_ipmitool_failure_is_502_with_its_last_error_line(self):
    stderr = "Error: Unable to establish IPMI v2 / RMCP+ session\n\n"
    failed, _ = self.run_bootdev(return_value=SimpleNamespace(returncode=1, stderr=stderr))
    self.assertEqual(failed, FAILED)
    self.assertNotIn("s3cret", failed["details"])
    self.assertTrue(bootdev.bootdev_failed(failed))

  def test_no_error_output(self):
    failed, _ = self.run_bootdev(return_value=SimpleNamespace(returncode=1, stderr=""))
    self.assertEqual(failed["status"], 502)
    self.assertIn("ipmitool exited 1: no error output", failed["details"])

  def test_timeout_is_504(self):
    failed, _ = self.run_bootdev(side_effect=subprocess.TimeoutExpired(cmd="ipmitool", timeout=30))
    self.assertEqual(failed["status"], 504)
    self.assertIn("didn't answer within 30s", failed["details"])

  def test_missing_ipmitool_is_500(self):
    failed, _ = self.run_bootdev(side_effect=FileNotFoundError(2, "No such file or directory"))
    self.assertEqual(failed["status"], 500)
    self.assertIn("couldn't run ipmitool: No such file or directory", failed["details"])

  def test_bootdev_failed(self):
    for result in (None, {"status": 200}, {"status": 409}, {"status": "400"}, "OK"):
      self.assertFalse(bootdev.bootdev_failed(result), result)


class PXEBootdevTestCase(ProvisionTestCase):
  """ A PXE-bootable system with a BMC, fake IPMI and a fake ipmitool result. """

  def setUp(self):
    super().setUp()
    self.client.force_login(self.user)
    NetworkInterface.objects.create(system=self.system, name="eth0", ipaddress="10.0.0.30", bootable=True)
    self.bmc = SystemBMC.objects.create(system=self.system, ipaddress="10.0.2.30", username="admin", password="pw")
    self.ipmi = mock.MagicMock()
    for target in ("systems.views.pyipmi.create_connection", "systems.admin.pyipmi.create_connection"):
      patcher = mock.patch(target, return_value=self.ipmi)
      patcher.start()
      self.addCleanup(patcher.stop)
    patcher = mock.patch("builtins.print")
    patcher.start()
    self.addCleanup(patcher.stop)

  def bootdev(self, result):
    """ Make set_pxe_bootdev() return result (None = it worked) in the view and the admin. """
    for target in ("systems.views.set_pxe_bootdev", "systems.admin.set_pxe_bootdev"):
      patcher = mock.patch(target, return_value=result)
      patcher.start()
      self.addCleanup(patcher.stop)

  def set_provision(self, value):
    self.system.provision = value
    self.system.save()

  def provision(self):
    self.system.refresh_from_db()
    return self.system.provision


class PXEBootdevAPITests(PXEBootdevTestCase):
  """ Issue #311: GET /power/pxe/ doesn't reset a node whose boot device wasn't set, and changes nothing. """

  def get(self, url):
    return self.client.get(url, CONTENT_TYPE="application/json")

  def test_failure_is_reported_in_the_entry_and_nothing_is_reset(self):
    self.bootdev(FAILED)
    for url in (f"/power/pxe/?hostname={self.system.hostname}", f"/power/pxe/?id={self.system.id}",
                f"/power/pxeefi/?ipaddress={self.bmc.ipaddress}"):
      with self.subTest(url=url):
        self.set_provision(False)
        response = self.get(url)
        # one rule for every form: HTTP 200, the failure inside the BMC's entry.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {str(self.bmc): FAILED})
        # put back to what it was.
        self.assertFalse(self.provision())
    self.ipmi.chassis_control_hard_reset.assert_not_called()
    self.ipmi.chassis_control_power_cycle.assert_not_called()
    self.ipmi.chassis_control_power_up.assert_not_called()

  def test_failure_keeps_a_provision_flag_that_was_already_set(self):
    self.bootdev(FAILED)
    self.set_provision(True)
    for url in (f"/power/pxe/?hostname={self.system.hostname}", f"/power/pxe/?id={self.system.id}"):
      self.get(url)
      self.assertTrue(self.provision())

  def test_success_sets_provision_and_resets(self):
    self.bootdev(None)
    for url in (f"/power/pxe/?hostname={self.system.hostname}", f"/power/pxe/?id={self.system.id}"):
      with self.subTest(url=url):
        self.set_provision(False)
        response = self.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()[str(self.bmc)])
        self.assertTrue(self.provision())
    self.assertEqual(self.ipmi.chassis_control_hard_reset.call_count, 2)


class PXEBootdevAdminTests(PXEBootdevTestCase):
  """ Issue #311: the admin's PXE Boot actions report a failed boot device and don't reset. """

  def run_action(self, action):
    response = self.client.post("/admin/systems/system/", {"action": action, "_selected_action": [self.system.pk]}, follow=True)
    self.assertEqual(response.status_code, 200)
    return [str(m) for m in response.context["messages"]]

  def test_failure_is_an_error_message_and_nothing_changes(self):
    self.bootdev(FAILED)
    for action in ("sys_pxe", "sys_pxe_efi"):
      with self.subTest(action=action):
        self.set_provision(False)
        messages = self.run_action(action)
        self.assertIn(f"{self.system.hostname}: {FAILED['details']}", messages)
        self.assertFalse(self.provision())
    self.ipmi.chassis_control_hard_reset.assert_not_called()

  def test_success_says_so(self):
    self.bootdev(None)
    self.set_provision(False)
    messages = self.run_action("sys_pxe")
    self.assertIn(f"{self.system.hostname}: set to PXE boot and reset.", messages)
    self.assertTrue(self.provision())
    self.ipmi.chassis_control_hard_reset.assert_called_once()
