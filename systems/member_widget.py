""" Picking a set of systems in the admin by hostname (#497).

System Groups and Physical Disk Layouts can have thousands of member systems.
A plain multi-select posts one form field per member and runs into Django's
field limit (#464), so they use raw_id_fields, which post every member in one
comma-separated field (#467).  SystemMembersWidget keeps that one hidden
field but shows the members as hostname chips, with Django's lookup popup to
add one system, "Add many..." to paste hostnames, IDs or ranges, and a "show
all" list once there are more chips than fit.  Names are looked up through
SystemAdmin's admin-only lookup URL (lookup_systems below), not the REST API.
"""
import re

from django.contrib.admin.widgets import ManyToManyRawIdWidget
from django.urls import reverse

from .range_wizard import expand_range

CHIPS_SHOWN = 50
MAX_PASTED = 10000
# SQLite before 3.32 allows only 999 variables in a query, so big IN lists
# are looked up in chunks.
CHUNK = 900


def _pairs(field, values, *columns):
  """ System values_list(*columns) for every system whose field is in
  values, a chunk at a time. """
  from .models import System
  values = list(values)
  rows = []
  for i in range(0, len(values), CHUNK):
    rows.extend(System.objects.filter(**{f'{field}__in': values[i:i + CHUNK]}).values_list(*columns))
  return rows


def natural_key(member):
  """ Sort members by hostname with numbers in order (c2 before c10), and
  unknown IDs last; system_members.js sorts the same way. """
  hostname = member['hostname']
  if hostname is None:
    return (1, [], member['id'])
  parts = re.split(r'(\d+)', hostname.lower())
  return (0, [(0, int(p), '') if p.isdigit() else (1, 0, p) for p in parts if p], member['id'])


class SystemMembersWidget(ManyToManyRawIdWidget):
  """ A raw-ID many-to-many field to System, shown as hostname chips. """
  template_name = 'admin/widgets/system_members.html'
  input_type = 'hidden'

  # The input is hidden but the widget isn't: without this Django treats the
  # field as hidden and the admin hides its whole row.
  @property
  def is_hidden(self):
    return False

  class Media:
    js = ['systems/admin/js/system_members.js']
    css = {'all': ['systems/admin/css/system_members.css']}

  def get_context(self, name, value, attrs):
    context = super().get_context(name, value, attrs)
    ids = []
    for v in (value or []):
      try:
        ids.append(int(v))
      except (TypeError, ValueError):
        continue
    names = dict(_pairs('pk', ids, 'pk', 'hostname'))
    members = sorted(({'id': pk, 'hostname': names.get(pk)} for pk in ids), key=natural_key)
    context['members'] = members
    context['members_shown'] = members[:CHIPS_SHOWN]
    context['members_hidden'] = max(len(members) - CHIPS_SHOWN, 0)
    context['chips_shown'] = CHIPS_SHOWN
    context['lookup_systems_url'] = reverse('admin:systems_system_lookup')
    context['members_json_id'] = f"{context['widget']['attrs'].get('id', name)}_members"
    return context


class SystemMembersMixin:
  """ For a ModelAdmin with `systems` in raw_id_fields: show it with
  SystemMembersWidget. """

  def formfield_for_manytomany(self, db_field, request, **kwargs):
    formfield = super().formfield_for_manytomany(db_field, request, **kwargs)
    if db_field.name == 'systems' and formfield is not None:
      formfield.widget = SystemMembersWidget(db_field.remote_field, self.admin_site, using=kwargs.get('using'))
    return formfield


def lookup_systems(ids=None, text=None):
  """ The systems for a list of IDs, or for pasted text: hostnames, IDs or
  ranges like c[001-100], separated by commas, spaces or new lines.  A bare
  number is an ID, or else a hostname.  Returns {"found": [{"id",
  "hostname"}...] in the order given, without repeats, "not_found": [entries
  that matched nothing], "error": a message, or None}. """
  if ids is not None:
    entries = [e for e in re.split(r'[\s,]+', ids) if e]
  else:
    entries = [e for e in re.split(r'[\s,]+', text or '') if e]
  # expand ranges first, so the cap counts what they stand for.
  wanted, not_found = [], []
  for entry in entries:
    if '[' in entry:
      try:
        wanted.extend(expand_range(entry))
      except ValueError as e:
        not_found.append(f"{entry} ({e})")
    else:
      wanted.append(entry)
    if len(wanted) > MAX_PASTED:
      return {'found': [], 'not_found': [], 'error': f"That's over {MAX_PASTED} systems; add them in smaller batches."}

  numbers = {int(w) for w in wanted if w.isdigit()}
  by_id = dict(_pairs('pk', numbers, 'pk', 'hostname'))
  names = [w for w in wanted if not (w.isdigit() and int(w) in by_id)] if ids is None else []
  by_name = {h: pk for pk, h in _pairs('hostname', set(names), 'pk', 'hostname')}

  found, seen = [], set()
  for w in wanted:
    if w.isdigit() and int(w) in by_id:
      pk, hostname = int(w), by_id[int(w)]
    elif w in by_name:
      pk, hostname = by_name[w], w
    else:
      not_found.append(w)
      continue
    if pk not in seen:
      seen.add(pk)
      found.append({'id': pk, 'hostname': hostname})
  return {'found': found, 'not_found': not_found, 'error': None}
