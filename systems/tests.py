from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase
from systems.views import SystemPowerAPIView


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
