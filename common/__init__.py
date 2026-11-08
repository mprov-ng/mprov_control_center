import yaml

# How the config of a System or SystemImage is built from the layers it
# inherits from.  The layers apply in this order, each one over the last:
#
#   OS Distro -> System Groups (by name) -> System Image -> System
#
# A System's groups are its own groups plus its image's groups, each applied
# once.  A System Image's layers are its distro, its groups and itself.
#
# - install_kernel_cmdline and initial_mods append down the stack (cmdline
#   joined with spaces, modules with commas).  A value starting with "="
#   replaces everything above it instead.
# - tmpfs_root_size and prov_interface overwrite.  0 or empty inherits.
# - config_params is YAML.  The layers are merged by top-level key: a key set
#   lower down replaces that key's whole value, other keys are kept.  A block
#   that is only blank lines and # comments inherits.  A block that isn't valid
#   YAML, or isn't a mapping (or a list of mappings), is skipped and reported.
# - scripts and the ansible playbooks, roles and collections are the union of
#   every layer, by slug.
# - files (managed files, #519) are the union of the distro, groups and image
#   layers, by slug, of the files that have a destination.  Two files with
#   the same destination: the later layer's wins, and the conflict is
#   reported.  Systems don't add files: an image is built once for all its
#   systems.
#
# The script runner in mprov_jobserver merges the same way, so keep the two
# in step.

APPEND_FIELDS = {'install_kernel_cmdline': ' ', 'initial_mods': ','}
OVERWRITE_FIELDS = ['tmpfs_root_size', 'prov_interface']
LIST_FIELDS = ['scripts', 'ansibleplaybooks', 'ansibleroles', 'ansiblecollections']


def has_content(value):
  """ True if value has a line that isn't blank or a # comment, so an
  inherited field set to only comments doesn't override the layer below. """
  return any(line.strip() and not line.lstrip().startswith("#") for line in value.split("\n"))


def config_layers(obj):
  """ The objects obj inherits its config from, in the order they apply, ending
  with obj itself. """
  if obj._meta.model_name == 'system':
    image = obj.systemimage
    groups = list(obj.systemgroups.all()) if obj.pk is not None else []
  else:
    image = obj
    groups = []
  distro = image.osdistro if image is not None else None
  if image is not None and image.pk is not None:
    groups += list(image.systemgroups.all())
  groups = sorted({group.pk: group for group in groups}.values(), key=lambda group: (group.name, group.pk))

  layers = []
  if distro is not None:
    layers.append(distro)
  layers += groups
  if image is not None and image is not obj:
    layers.append(image)
  layers.append(obj)
  return layers


def parse_config_params(value):
  """ The config_params YAML of one layer as a dict, or None if the layer
  inherits.  Raises ValueError if it can't be used. """
  if value is None or not has_content(value):
    return None
  try:
    parsed = yaml.safe_load(value)
  except yaml.YAMLError as e:
    raise ValueError(f"not valid YAML: {e}")
  if parsed is None:
    return None
  if isinstance(parsed, dict):
    return parsed
  if isinstance(parsed, list) and all(isinstance(entry, dict) for entry in parsed):
    merged = {}
    for entry in parsed:
      merged.update(entry)
    return merged
  raise ValueError("not a mapping of names to values")


def render_config(obj):
  """ Merge the config of a System or SystemImage from its layers (see the
  comment at the top of this module).  Returns a dict with:

  - layers: the layer objects, in order.
  - fields: {field: {'value': ..., 'sources': [layer, ...]}} for the boot
    fields that some layer sets.
  - config_params: {key: {'value': ..., 'source': layer}}.
  - scripts, ansibleplaybooks, ansibleroles, ansiblecollections:
    [{'item': object, 'sources': [layer, ...]}], in the order they were found.
  - errors: [(layer, message)] for config_params blocks that were skipped.

  flat_config() turns this into the plain dict nodes see.
  """
  layers = config_layers(obj)
  fields = {}
  config_params = {}
  lists = {name: {} for name in LIST_FIELDS}
  errors = []

  for layer in layers:
    field_names = {field.name for field in layer._meta.get_fields()}

    for field, separator in APPEND_FIELDS.items():
      value = getattr(layer, field) if field in field_names else None
      if not value or not has_content(value):
        continue
      if value.startswith("="):
        fields[field] = {'value': value[1:], 'sources': [layer]}
      elif field in fields:
        fields[field]['value'] = (fields[field]['value'] + separator + value).lstrip(separator)
        fields[field]['sources'].append(layer)
      else:
        fields[field] = {'value': value, 'sources': [layer]}

    for field in OVERWRITE_FIELDS:
      value = getattr(layer, field) if field in field_names else None
      if isinstance(value, str) and not has_content(value):
        continue
      if value:
        fields[field] = {'value': value, 'sources': [layer]}

    try:
      params = parse_config_params(getattr(layer, 'config_params', None))
    except ValueError as e:
      errors.append((layer, f"Configuration Parameters skipped, {e}"))
      params = None
    for key, value in (params or {}).items():
      config_params[key] = {'value': value, 'source': layer}

    if layer.pk is None:
      continue
    for name in LIST_FIELDS:
      if name not in field_names:
        continue
      for item in getattr(layer, name).all():
        entry = lists[name].setdefault(item.pk, {'item': item, 'sources': []})
        entry['sources'].append(layer)

  rendered = {
    'layers': layers,
    'fields': fields,
    'config_params': config_params,
    'errors': errors,
  }
  for name in LIST_FIELDS:
    rendered[name] = list(lists[name].values())
  rendered['files'], rendered['file_conflicts'] = merge_files(layers)
  rendered['image'] = next((layer for layer in reversed(layers) if layer._meta.model_name == 'systemimage'), None)
  return rendered


def merge_files(layers):
  """ The managed files of these layers (#519): [{'item': File, 'sources':
  [layer, ...]}] for the files with a destination, by slug, and the conflicts
  as [{'dest_path', 'replaced': File, 'by': File, 'layer': layer}], where a
  later layer's file replaced an earlier one at the same destination. """
  by_dest = {}
  conflicts = []
  for layer in layers:
    if layer.pk is None or layer._meta.model_name == 'system' or not hasattr(layer, 'files'):
      continue
    for item in layer.files.exclude(dest_path="").order_by('dest_path', 'slug'):
      current = by_dest.get(item.dest_path)
      if current is not None and current['item'].pk == item.pk:
        current['sources'].append(layer)
        continue
      if current is not None:
        conflicts.append({'dest_path': item.dest_path, 'replaced': current['item'], 'by': item, 'layer': layer})
      by_dest[item.dest_path] = {'item': item, 'sources': [layer]}
  return sorted(by_dest.values(), key=lambda entry: entry['item'].dest_path), conflicts


def file_entry(item, image):
  """ One managed file as the job server sees it in config.files (#519).  url
  is a path on the mPCC: the copy rendered for this image for a template,
  else the uploaded file. """
  if item.template and image is not None:
    # root-relative, with any path prefix the mPCC is served under
    from django.urls import reverse
    url = reverse('systemimage-file', kwargs={'pk': image.slug, 'slug': item.slug})
  else:
    url = item.filename.url if item.filename else ""
  return {'slug': item.slug, 'name': item.name, 'version': item.version, 'dest_path': item.dest_path,
          'owner': item.owner, 'group': item.group, 'mode': item.mode, 'template': item.template, 'url': url}


def flat_config(rendered):
  """ The rendered config as plain values: the boot fields that are set,
  config_params as a dict, and each script and ansible list as slugs. """
  config = {field: entry['value'] for field, entry in rendered['fields'].items()}
  config['config_params'] = {key: entry['value'] for key, entry in rendered['config_params'].items()}
  for name in LIST_FIELDS:
    config[name] = [entry['item'].pk for entry in rendered[name]]
  config['files'] = [file_entry(entry['item'], rendered.get('image')) for entry in rendered.get('files', [])]
  return config
