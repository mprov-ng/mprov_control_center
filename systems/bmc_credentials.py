""" Setting the stored BMC credentials of many systems at once (#374). """
import logging

from django import forms
from django.db import transaction
from django.utils import timezone

from systems.models import SystemBMC

bmc_log = logging.getLogger('mprov.bmc')


class BMCCredentialsForm(forms.Form):
  STORE, CHANGE, CHECK = "store", "change", "check"
  # missing means store, as before #486
  mode = forms.ChoiceField(label="What to do", initial=STORE, required=False, widget=forms.RadioSelect, choices=[
    (STORE, "Store them in the mPCC only (change the BMCs yourself)"),
    (CHANGE, "Change them on the BMCs, then store what the BMCs accepted"),
    (CHECK, "Check that the stored credentials work on the BMCs (changes nothing)"),
  ], help_text="Changing or checking on the BMCs is done by a job server on each BMC's network (#486).")
  username = forms.CharField(max_length=255, required=False, label="BMC User",
    help_text="Leave blank to keep each BMC's current user.")
  password = forms.CharField(max_length=100, required=False, label="New BMC Password",
    widget=forms.PasswordInput(render_value=False))
  confirm = forms.CharField(max_length=100, required=False, label="Confirm Password",
    widget=forms.PasswordInput(render_value=False),
    help_text="Leave both password fields blank to keep each BMC's current password.")

  def clean(self):
    data = super().clean()
    mode = data.get('mode') or self.STORE
    if mode != self.STORE:
      from bmcrotate.logic import available
      if not available():
        raise forms.ValidationError("No job server runs the bmc-rotate module, so the BMCs can't be changed or "
                                    "checked. Add it to a job server on the BMCs' network (MPROV_MODS).")
    if mode == self.CHECK:
      return data
    if data.get('password', '') != data.get('confirm', ''):
      self.add_error('confirm', "The passwords don't match.")
    elif not data.get('username') and not data.get('password'):
      raise forms.ValidationError("Enter a new user, a new password, or both.")
    return data


def split_by_bmc(systems):
  """ (systems with a BMC, systems without one), each sorted by hostname. """
  with_bmc = set(SystemBMC.objects.filter(system__in=systems).values_list('system_id', flat=True))
  systems = sorted(systems, key=lambda system: system.hostname)
  return [s for s in systems if s.pk in with_bmc], [s for s in systems if s.pk not in with_bmc]


def summarize(hostnames, limit=5):
  """ "c01, c02, c03" or "c01, c02, ... (40 more)", for a log line or message. """
  if len(hostnames) <= limit:
    return ", ".join(hostnames)
  return ", ".join(hostnames[:limit]) + f", ... ({len(hostnames) - limit} more)"


def set_bmc_credentials(systems, username, password, user):
  """ Set the stored username and/or password (a blank one is kept) on every
  BMC of these systems.  A queryset update: the credentials don't affect the
  pxe/dns/dhcp config that a SystemBMC save queues jobs for.  Returns
  (systems updated, systems skipped because they have no BMC). """
  updated, skipped = split_by_bmc(systems)
  changes = {'credentials_changed': timezone.now()}
  if username:
    changes['username'] = username
  if password:
    changes['password'] = password
  with transaction.atomic():
    SystemBMC.objects.filter(system__in=updated).update(**changes)
  bmc_log.info(
    f"bmc: credentials set on {len(updated)} systems ({summarize([s.hostname for s in updated]) or 'none'}"
    f"{f'; {len(skipped)} skipped with no BMC' if skipped else ''}) by {user}, "
    f"user {'changed' if username else 'kept'}, password {'changed' if password else 'kept'}")
  return updated, skipped
