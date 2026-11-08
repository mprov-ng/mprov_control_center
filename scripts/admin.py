from django.contrib import admin
from django.conf import settings
from django.db import models
from .models import Script, AnsiblePlaybook, AnsibleRole, AnsibleCollection, File
import os

from common.admin import LiveSearchMixin

# version is a BigIntegerField, so its input gets min=-2**63.  A number input
# steps from its min, and browsers can't step by 1 from there in floating
# point, so the spinner arrows did nothing (#172).  Versions start at 1.
VERSION_OVERRIDES = {models.BigIntegerField: {'min_value': 1}}

# The Config Management lists sort by name and search and filter as you type (#496).
class ScriptAdmin(LiveSearchMixin, admin.ModelAdmin):
  """ Scripts that the script runner runs in images and on nodes. """
  ordering = ['name']
  search_fields = ['name', 'filename']
  list_filter = ['scriptType']
  model = Script
  formfield_overrides = VERSION_OVERRIDES
  readonly_fields = ['slug']
  list_display = ['name', 'filename', 'scriptType']
  exclude = ('slug',)
  change_form_template ='admin/scripts_change_form.html'

  def get_form(self, request, obj=None, **kwargs):
      """
      Override to populate the content field with the file contents when editing existing scripts.
      """
      form = super().get_form(request, obj, **kwargs)
      if obj and not obj.content:  # Editing existing object and content is empty
          try:
              # Try to read the file content
              file_path = obj.filename.path if hasattr(obj.filename, 'path') else os.path.join(settings.MEDIA_ROOT, obj.filename.name)
              if os.path.exists(file_path):
                  with open(file_path, 'r', encoding='utf-8') as f:
                      obj.content = f.read()
          except Exception as e:
              print(f"Error reading file for admin form: {e}")
      return form


class FileAdmin(LiveSearchMixin, admin.ModelAdmin):
  """ Files uploaded to the mPCC, and where they're placed in images (#519). """
  ordering = ['name']
  search_fields = ['name', 'filename', 'dest_path']
  model = File
  formfield_overrides = VERSION_OVERRIDES
  readonly_fields = ['slug']
  list_display = ['name', 'filename', 'dest_path', 'owner', 'group', 'mode', 'template']
  exclude = ('slug',)

  def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
    if request.method == "GET":
      from django.contrib import messages
      messages.warning(request, "Anything placed in an image can be read by anyone who can download the image. "
                                "Never put passwords, keys or other secrets in a managed file.")
    return super().changeform_view(request, object_id, form_url, extra_context)

  def get_form(self, request, obj=None, **kwargs):
    form = super().get_form(request, obj, **kwargs)
    superuser = request.user.is_superuser

    class Form(form):
      def clean(self):
        data = super().clean()
        mode = data.get('mode') or ""
        if len(mode) == 4 and int(mode[0], 8) & 0o6 and not superuser:
          self.add_error('mode', "Only a superuser may set a setuid or setgid mode.")
        return data
    return Form

  def save_model(self, request, obj, form, change):
    super().save_model(request, obj, form, change)
    if change and obj.dest_path:
      from scripts.files import images_using, tell_rebuild
      tell_rebuild(self, request, images_using([obj]), f"the file {obj.name}")

class AnsiblePlaybookAdmin(LiveSearchMixin, admin.ModelAdmin):
  """ Ansible playbooks. """
  ordering = ['name']
  search_fields = ['name', 'filename']
  list_filter = ['scriptType']
  model = AnsiblePlaybook
  formfield_overrides = VERSION_OVERRIDES
  readonly_fields = ['slug']
  list_display = ['name', 'filename', 'scriptType']
  exclude = ('slug',)

  
class AnsibleRoleAdmin(LiveSearchMixin, admin.ModelAdmin):
  """ Ansible roles. """
  ordering = ['name']
  search_fields = ['name', 'roleurl']
  list_filter = ['scriptType']
  model = AnsibleRole
  formfield_overrides = VERSION_OVERRIDES
  readonly_fields = ['slug']
  list_display = ['name', 'roleurl', 'scriptType']
  exclude = ('slug',)

class AnsibleCollectionAdmin(LiveSearchMixin, admin.ModelAdmin):
  """ Ansible collections. """
  ordering = ['name']
  search_fields = ['name', 'collectionurl']
  list_filter = ['scriptType']
  model = AnsibleCollection
  formfield_overrides = VERSION_OVERRIDES
  readonly_fields = ['slug']
  list_display = ['name', 'collectionurl', 'scriptType']
  exclude = ('slug',)


admin.site.register(File, FileAdmin)
admin.site.register(AnsiblePlaybook, AnsiblePlaybookAdmin)
admin.site.register(AnsibleRole, AnsibleRoleAdmin)
admin.site.register(AnsibleCollection, AnsibleCollectionAdmin)
admin.site.register(Script, ScriptAdmin)
