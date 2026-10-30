import os
import subprocess

# how long ipmitool may take to set the boot device before we give up (#311).
BOOTDEV_TIMEOUT = 30

# the per-BMC result statuses set_pxe_bootdev() reports a failure with.
BOOTDEV_FAILED = (500, 502, 504)


def set_pxe_bootdev(bmc, efi=False, timeout=BOOTDEV_TIMEOUT):
  """
  Set the BMC's next boot device to PXE (UEFI if efi).  Returns None when
  ipmitool says it worked, else the power API's per-BMC result for the
  failure (#311): 502 when ipmitool fails, 504 when it times out, 500 when
  it can't run.  The caller must not reset the node then.
  """
  # bootdev is not implemented in python-ipmi (pyipmi), so we issue a raw
  # ipmitool command.  -E reads the password from IPMI_PASSWORD, keeping it
  # out of the process list.
  cmd = ["/usr/bin/ipmitool", "-Ilanplus", f"-U{bmc.username}", "-E", f"-H{bmc.ipaddress}", "chassis", "bootdev", "pxe"]
  if efi:
    cmd.append("options=efiboot")
  env = {**os.environ, "IPMI_PASSWORD": bmc.password or ""}
  try:
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout)
  except subprocess.TimeoutExpired:
    return _failed(504, f"ipmitool didn't answer within {timeout}s")
  except OSError as e:
    return _failed(500, f"couldn't run ipmitool: {e.strerror or e}")
  if result.returncode != 0:
    lines = [line.strip() for line in (result.stderr or "").splitlines() if line.strip()]
    reason = lines[-1] if lines else "no error output"
    return _failed(502, f"ipmitool exited {result.returncode}: {reason}")
  return None


def bootdev_failed(result):
  """ Whether a per-BMC power result is a set_pxe_bootdev() failure. """
  return isinstance(result, dict) and result.get('status') in BOOTDEV_FAILED


def _failed(status, reason):
  print(f"Error setting PXE: {reason}")
  return {'details': f"Setting the boot device to PXE failed ({reason}).  It was not reset.",
          'status': status, 'chassis_status': 'unknown'}
