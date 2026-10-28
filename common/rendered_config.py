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


def source(layer, obj):
  """ How the tab names a layer: the object itself is "this system" (or
  image), the others link to their own change page. """
  kind = LAYER_LABELS.get(layer._meta.model_name, layer._meta.verbose_name)
  if layer is obj:
    return {'label': f"this {kind.lower()}", 'url': None}
  return {'label': f"{kind}: {layer}", 'url': admin_url(layer)}


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
  fields = [
    {'label': label, 'value': rendered['fields'][field]['value'],
     'sources': [source(layer, obj) for layer in rendered['fields'][field]['sources']]}
    for field, label in FIELD_LABELS.items() if field in rendered['fields']
  ]
  params = [
    {'key': key, 'value': show(entry['value']), 'source': source(entry['source'], obj)}
    for key, entry in rendered['config_params'].items()
  ]
  lists = []
  for name in LIST_FIELDS:
    items = [
      {'name': entry['item'].name, 'url': admin_url(entry['item']),
       'type': entry['item'].scriptType.name if entry['item'].scriptType else '',
       'sources': [source(layer, obj) for layer in entry['sources']]}
      for entry in rendered[name]
    ]
    lists.append({'label': LIST_LABELS[name], 'items': items})
  return {
    'kind': LAYER_LABELS.get(obj._meta.model_name, obj._meta.verbose_name).lower(),
    'layers': [source(layer, obj) for layer in rendered['layers']],
    'errors': [{'source': source(layer, obj), 'message': message} for layer, message in rendered['errors']],
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
