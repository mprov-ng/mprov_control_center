""" The "Add systems from a range" admin wizard (#38): many systems, each with
a NIC, a switch port and a BMC, from one hostname pattern like c[001-100]. """
import ipaddress
import logging
import re
from dataclasses import dataclass, field

from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.db import transaction

from disklayouts.models import DiskLayout
from networks.models import Network, Switch, SwitchPort
from systems.models import NetworkInterface, System, SystemBMC, SystemGroup, SystemImage, SystemLocation, SystemModel

wizard_log = logging.getLogger('mprov.systems')

MAX_SYSTEMS = 1000
RANGE = re.compile(r"^([^\[\]]*)\[(\d+)-(\d+)\]([^\[\]]*)$")
MAC = re.compile(r"^[0-9a-f]{2}([:-][0-9a-f]{2}){5}$")

# copied from "Copy settings from"; NICs, BMCs and the serial number never are.
COPIED_FIELDS = ['systemimage', 'systemmodel', 'location', 'stateful', 'provision', 'config_params',
                 'install_kernel_cmdline', 'tmpfs_root_size', 'initial_mods', 'prov_interface']
COPIED_M2M = ['systemgroups', 'disks', 'scripts', 'ansibleplaybooks', 'ansibleroles', 'ansiblecollections']


def expand_range(pattern):
  """ The names a pattern like "c[001-100]" or "1/[1-40]" stands for, in
  order, zero-padded to the width of the start number.  Raises ValueError
  saying what's wrong with the pattern. """
  match = RANGE.match(pattern.strip())
  if match is None:
    raise ValueError("Use one range in brackets, like c[001-100].")
  prefix, start, end, suffix = match.groups()
  first, last = int(start), int(end)
  if first > last:
    raise ValueError(f"The range starts after it ends ({start}-{end}).")
  if last - first + 1 > MAX_SYSTEMS:
    raise ValueError(f"That's {last - first + 1} names; at most {MAX_SYSTEMS} at a time.")
  width = len(start)
  return [f"{prefix}{n:0{width}d}{suffix}" for n in range(first, last + 1)]


def address_range(start, count, network):
  """ count addresses counting up from start, all inside network (if it
  has a usable subnet).  Raises ValueError. """
  try:
    first = ipaddress.ip_address(start)
  except ValueError:
    raise ValueError(f"{start} isn't an IP address.") from None
  try:
    addresses = [first + i for i in range(count)]
  except ipaddress.AddressValueError:
    raise ValueError(f"{count} addresses from {start} run past the end of the address space.") from None
  if network is not None:
    try:
      subnet = ipaddress.ip_network(f"{network.subnet}/{network.netmask}", strict=False)
    except ValueError:
      subnet = None
    if subnet is not None and subnet.version == first.version:
      outside = [a for a in addresses if a not in subnet
                 or (subnet.version == 4 and subnet.prefixlen < 31 and a in (subnet.network_address, subnet.broadcast_address))]
      if outside:
        raise ValueError(f"{outside[0]} isn't a host address in {network.name} ({subnet}); "
                         f"{count} addresses from {start} don't fit.")
  return [str(a) for a in addresses]


def parse_macs(text):
  """ One MAC per line (blank lines ignored), lower-cased with colons. """
  return [line.strip().lower().replace("-", ":") for line in text.splitlines() if line.strip()]


class SwitchChoiceField(forms.ModelChoiceField):
  """ Switches by hostname: Switch has no __str__ of its own. """
  def label_from_instance(self, obj):
    return obj.hostname


class RangeWizardForm(forms.Form):
  hostnames = forms.CharField(max_length=255, label="Hostnames", help_text="One range in brackets, e.g. c[001-100]; "
    f"the start number's width sets the zero-padding.  At most {MAX_SYSTEMS}.")

  copy_from = forms.ModelChoiceField(System.objects.all(), required=False, label="Copy settings from",
    help_text="An existing system whose image, model, groups, location, disks, scripts, Ansible, config and boot "
              "options the new ones start with.  Its NICs, BMC and serial number are never copied.")
  systemimage = forms.ModelChoiceField(SystemImage.objects.all(), required=False, label="System Image")
  systemmodel = forms.ModelChoiceField(SystemModel.objects.all(), required=False, label="System Model")
  location = forms.ModelChoiceField(SystemLocation.objects.all(), required=False, label="Location")
  systemgroups = forms.ModelMultipleChoiceField(SystemGroup.objects.all(), required=False, label="System Groups",
    widget=FilteredSelectMultiple("System Groups", False))
  disks = forms.ModelMultipleChoiceField(DiskLayout.objects.all(), required=False, label="Disk Layouts",
    widget=FilteredSelectMultiple("Disk Layouts", False))
  stateful = forms.TypedChoiceField(required=False, label="Stateful System?", empty_value=None,
    choices=[("", "Copied, or no"), ("yes", "Yes"), ("no", "No")], coerce=lambda v: v == "yes")
  provision = forms.TypedChoiceField(required=False, label="Provision?", empty_value=None,
    choices=[("", "Copied, or yes"), ("yes", "Yes"), ("no", "No")], coerce=lambda v: v == "yes")

  nic_name = forms.CharField(max_length=50, initial="eth0", required=False, label="NIC Name",
    help_text="A NIC is added to each system if a network, IP, MAC or switch port is given below.")
  nic_network = forms.ModelChoiceField(Network.objects.all(), required=False, label="NIC Network")
  nic_start_ip = forms.GenericIPAddressField(required=False, label="First IP Address",
    help_text="Counts up by one per system, and must stay inside the network.")
  nic_bootable = forms.BooleanField(required=False, initial=True, label="Bootable NIC?")
  macs = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}), label="MAC Addresses",
    help_text="Optional: one per line, in hostname order, one for every system.  Leave blank for N.A.D.S. to fill in.")
  switch = SwitchChoiceField(Switch.objects.order_by('hostname'), required=False, label="Switch")
  port_pattern = forms.CharField(max_length=100, required=False, label="Switch Ports",
    help_text="Optional: e.g. 1/[1-40], one existing port per system, in order.  A NIC on a switch port with no MAC "
              "is what N.A.D.S. fills in when the node first boots.")

  bmc_network = forms.ModelChoiceField(Network.objects.all(), required=False, label="BMC Network")
  bmc_start_ip = forms.GenericIPAddressField(required=False, label="First BMC IP Address",
    help_text="A BMC is added to each system if this is given.")
  bmc_username = forms.CharField(max_length=255, required=False, label="BMC User")
  bmc_password = forms.CharField(max_length=100, required=False, label="BMC Password",
    widget=forms.PasswordInput(render_value=False))

  def clean(self):
    data = super().clean()
    if not data.get('hostnames'):
      return data
    try:
      data['hostname_list'] = expand_range(data['hostnames'])
    except ValueError as err:
      self.add_error('hostnames', str(err))
      return data
    if data.get('port_pattern') and not data.get('switch'):
      self.add_error('switch', "Choose the switch the ports are on.")
    if data.get('switch') and not data.get('port_pattern'):
      self.add_error('port_pattern', "Enter the ports, e.g. 1/[1-40].")
    if (data.get('bmc_network') or data.get('bmc_username') or data.get('bmc_password')) and not data.get('bmc_start_ip'):
      self.add_error('bmc_start_ip', "Enter the first BMC IP address to add BMCs.")
    if self.wants_nic(data) and not data.get('nic_name'):
      self.add_error('nic_name', "Enter the NIC name, e.g. eth0.")
    return data

  @staticmethod
  def wants_nic(data):
    return bool(data.get('nic_network') or data.get('nic_start_ip') or data.get('macs') or data.get('port_pattern'))


@dataclass
class PlannedSystem:
  hostname: str
  ip: str = None
  mac: str = None
  port: SwitchPort = None
  bmc_ip: str = None
  problems: list = field(default_factory=list)


@dataclass
class Plan:
  systems: list
  problems: list   # problems with the whole run, e.g. a MAC count mismatch

  @property
  def ok(self):
    return not self.problems and not any(s.problems for s in self.systems)


def plan_range(data):
  """ What the wizard would create from a valid RangeWizardForm's
  cleaned_data, with every problem that would stop it.  Changes nothing. """
  hostnames = data['hostname_list']
  count = len(hostnames)
  plan = Plan([PlannedSystem(h) for h in hostnames], [])

  def column(attr, values):
    for planned, value in zip(plan.systems, values):
      setattr(planned, attr, value)

  try:
    if data.get('nic_start_ip'):
      column('ip', address_range(data['nic_start_ip'], count, data.get('nic_network')))
  except ValueError as err:
    plan.problems.append(f"NIC addresses: {err}")
  try:
    if data.get('bmc_start_ip'):
      column('bmc_ip', address_range(data['bmc_start_ip'], count, data.get('bmc_network')))
  except ValueError as err:
    plan.problems.append(f"BMC addresses: {err}")

  if data.get('macs'):
    macs = parse_macs(data['macs'])
    if len(macs) != count:
      plan.problems.append(f"{len(macs)} MAC addresses for {count} systems; give one per system, or none.")
    else:
      column('mac', macs)

  if data.get('port_pattern') and data.get('switch'):
    try:
      names = expand_range(data['port_pattern'])
    except ValueError as err:
      plan.problems.append(f"Switch ports: {err}")
      names = None
    if names is not None and len(names) != count:
      plan.problems.append(f"{len(names)} switch ports for {count} systems; give one per system.")
    elif names is not None:
      ports = {p.name: p for p in SwitchPort.objects.filter(switch=data['switch'], name__in=names)}
      for planned, name in zip(plan.systems, names):
        planned.port = ports.get(name)
        if planned.port is None:
          planned.problems.append(f"There's no port {name} on {data['switch'].hostname}.")

  # clashes with what already exists, and within the run.
  for planned in System.objects.filter(hostname__in=hostnames).values_list('hostname', flat=True):
    next(p for p in plan.systems if p.hostname == planned).problems.append("A system with this hostname already exists.")
  ips = [p.ip for p in plan.systems if p.ip] + [p.bmc_ip for p in plan.systems if p.bmc_ip]
  used = set(NetworkInterface.objects.filter(ipaddress__in=ips).values_list('ipaddress', flat=True)) | \
         set(SystemBMC.objects.filter(ipaddress__in=ips).values_list('ipaddress', flat=True))
  seen = {}
  for ip in ips:
    seen[ip] = seen.get(ip, 0) + 1
  for planned in plan.systems:
    for label, ip in (("IP address", planned.ip), ("BMC IP address", planned.bmc_ip)):
      if ip and ip in used:
        planned.problems.append(f"{label} {ip} is already in use.")
      elif ip and seen[ip] > 1:
        planned.problems.append(f"{label} {ip} is used twice in this range.")
  macs = [p.mac for p in plan.systems if p.mac]
  used_macs = set(m.lower() for m in NetworkInterface.objects.filter(mac__in=macs).values_list('mac', flat=True))
  for planned in plan.systems:
    if planned.mac is None:
      continue
    if not MAC.match(planned.mac):
      planned.problems.append(f"{planned.mac} isn't a MAC address.")
    elif planned.mac in used_macs:
      planned.problems.append(f"MAC {planned.mac} is already on a NIC.")
    elif macs.count(planned.mac) > 1:
      planned.problems.append(f"MAC {planned.mac} is given twice.")
  ports = [p.port for p in plan.systems if p.port is not None]
  taken = set(NetworkInterface.objects.filter(switch_port__in=ports).values_list('switch_port_id', flat=True))
  for planned in plan.systems:
    if planned.port is not None and planned.port.pk in taken:
      planned.problems.append(f"Switch port {planned.port} is already used by a NIC.")
  return plan


def create_range(data, plan, user, bmc_password=None):
  """ Create the planned systems, all or none.  Returns them. """
  template = data.get('copy_from')
  overrides = {name: data[name] for name in ('systemimage', 'systemmodel', 'location', 'stateful', 'provision')
               if data.get(name) is not None}
  wants_nic = RangeWizardForm.wants_nic(data)
  created = []
  with transaction.atomic():
    for planned in plan.systems:
      fields = {name: getattr(template, name) for name in COPIED_FIELDS} if template else {}
      fields.update(overrides)
      system = System.objects.create(hostname=planned.hostname, created_by=user, **fields)
      for name in COPIED_M2M:
        if name in ('systemgroups', 'disks') and data.get(name):
          getattr(system, name).set(data[name])
        elif template is not None:
          getattr(system, name).set(getattr(template, name).all())
      if wants_nic:
        NetworkInterface.objects.create(system=system, name=data['nic_name'], ipaddress=planned.ip, mac=planned.mac,
                                        switch_port=planned.port, network=data.get('nic_network'),
                                        bootable=data.get('nic_bootable', False))
      if planned.bmc_ip:
        SystemBMC.objects.create(system=system, ipaddress=planned.bmc_ip, network=data.get('bmc_network'),
                                 username=data.get('bmc_username') or None, password=bmc_password or None)
      created.append(system)
  wizard_log.info(f"systems: added {len(created)} systems from {data['hostnames']} by {user}")
  return created
