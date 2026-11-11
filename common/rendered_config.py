import json

import yaml
from django.contrib import admin
from django.template.loader import render_to_string
from django.urls import NoReverseMatch, reverse

from common import LIST_FIELDS, flat_config, render_config

LAYER_LABELS = {
  'osdistro': 'OS Distribution',
  'systemgroup': 'System Group',
  'systemimage': 'System Image',
  'system': 'System',
}
FIELD_LABELS = {
  'install_kernel_cmdline': 'Install kernel command line',
  'initial_mods': 'Initial modules',
  'tmpfs_root_size': 'Root tmpfs size (GB)',
  'prov_interface': 'Provisioning interface',
}
LIST_LABELS = {
  'scripts': 'Scripts',
  'ansibleplaybooks': 'Ansible Playbooks',
  'ansibleroles': 'Ansible Roles',
  'ansiblecollections': 'Ansible Collections',
}


def admin_url(item):
  """ The admin change page of item, or None if it has none. """
  if item.pk is None:
    return None
  try:
    return reverse(f"admin:{item._meta.app_label}_{item._meta.model_name}_change", args=[item.pk])
  except NoReverseMatch:
    return None


def group_origins(obj):
  """ On a system, where each of its system groups comes from: {group pk:
  "S"} for a group of the system itself, "I" for one of its image, "S, I"
  for both (#553).  Empty for an image, whose groups are all its own. """
  if obj._meta.model_name != 'system' or obj.pk is None:
    return {}
  own = set(obj.systemgroups.values_list('pk', flat=True))
  image = obj.systemimage
  inherited = set(image.systemgroups.values_list('pk', flat=True)) if image is not None and image.pk is not None else set()
  return {pk: ", ".join(tag for tag, groups in (("S", own), ("I", inherited)) if pk in groups)
          for pk in own | inherited}


def source(layer, obj, origins=None):
  """ How the tab names a layer: the object itself is "this system" (or
  image), the others link to their own change page.  A system group is
  tagged with its origin from group_origins(), e.g. "System Group: gpu (I)". """
  kind = LAYER_LABELS.get(layer._meta.model_name, layer._meta.verbose_name)
  if layer is obj:
    return {'label': f"this {kind.lower()}", 'url': None}
  label = f"{kind}: {layer}"
  if layer._meta.model_name == 'systemgroup' and origins and layer.pk in origins:
    label += f" ({origins[layer.pk]})"
  return {'label': label, 'url': admin_url(layer)}


def show(value):
  """ A config_params value as the YAML it would be written as. """
  text = yaml.safe_dump(value, default_flow_style=False, sort_keys=False)
  # a plain scalar is dumped as a document of its own, ending in "...".
  if text.endswith("\n...\n"):
    text = text[:-len("...\n")]
  return text.strip()


def rendered_config_context(obj):
  """ The rendered config of a System or SystemImage, laid out for the
  admin/rendered_config.html template. """
  rendered = render_config(obj)
  origins = group_origins(obj)

  def source_of(layer):
    return source(layer, obj, origins)

  fields = [
    {'label': label, 'value': rendered['fields'][field]['value'],
     'sources': [source_of(layer) for layer in rendered['fields'][field]['sources']]}
    for field, label in FIELD_LABELS.items() if field in rendered['fields']
  ]
  params = [
    {'key': key, 'value': show(entry['value']), 'source': source_of(entry['source'])}
    for key, entry in rendered['config_params'].items()
  ]
  lists = []
  for name in LIST_FIELDS:
    items = [
      {'name': entry['item'].name, 'url': admin_url(entry['item']),
       'type': entry['item'].scriptType.name if entry['item'].scriptType else '',
       'sources': [source_of(layer) for layer in entry['sources']]}
      for entry in rendered[name]
    ]
    lists.append({'label': LIST_LABELS[name], 'items': items})
  files = [
    {'dest_path': entry['item'].dest_path, 'name': entry['item'].name, 'url': admin_url(entry['item']),
     'owner': f"{entry['item'].owner}:{entry['item'].group}", 'mode': entry['item'].mode,
     'template': entry['item'].template,
     'sources': [source_of(layer) for layer in entry['sources']]}
    for entry in rendered['files']
  ]
  file_warnings = [
    f"{c['dest_path']}: {c['by'].name} ({source_of(c['layer'])['label']}) replaces {c['replaced'].name}."
    for c in rendered['file_conflicts']
  ]
  if obj._meta.model_name == 'systemimage' and obj.pk is not None:
    # a template that doesn't render would fail this image's build: say so now
    from scripts.templating import render
    for entry in rendered['files']:
      if entry['item'].template:
        _, error = render(entry['item'], obj)
        if error:
          file_warnings.append(f"Template error, this image won't build: {error}")
  return {
    'files': files,
    'file_warnings': file_warnings,
    'kind': LAYER_LABELS.get(obj._meta.model_name, obj._meta.verbose_name).lower(),
    'layers': [source_of(layer) for layer in rendered['layers']],
    'errors': [{'source': source_of(layer), 'message': message} for layer, message in rendered['errors']],
    'fields': fields,
    'params': params,
    'lists': lists,
    'served': json.dumps(flat_config(rendered), indent=2, default=str),
  }


class RenderedConfigAdminMixin:
  """ Adds a Rendered Config tab to a ModelAdmin's change page, showing the
  object's merged config and where each value came from. """

  def get_readonly_fields(self, request, obj=None):
    fields = list(super().get_readonly_fields(request, obj))
    if obj is not None:
      fields.append('rendered_config')
    return fields

  def get_fieldsets(self, request, obj=None):
    # jazzmin shows each fieldset as a tab; the config only exists once the object does.
    fieldsets = list(super().get_fieldsets(request, obj))
    if obj is not None:
      fieldsets.append(('Rendered Config', {'fields': ['rendered_config']}))
    return fieldsets

  @admin.display(description='Rendered configuration')
  def rendered_config(self, obj):
    return render_to_string('admin/rendered_config.html', rendered_config_context(obj))
