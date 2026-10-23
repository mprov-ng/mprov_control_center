from django.contrib import admin
from django.conf import settings
from django.db import models
from .models import Script, AnsiblePlaybook, AnsibleRole, AnsibleCollection, File
import os

# version is a BigIntegerField, so its input gets min=-2**63.  A number input
# steps from its min, and browsers can't step by 1 from there in floating
# point, so the spinner arrows did nothing (#172).  Versions start at 1.
VERSION_OVERRIDES = {models.BigIntegerField: {'min_value': 1}}

class ScriptAdmin(admin.ModelAdmin):
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


class FileAdmin(admin.ModelAdmin):
  model = File
  formfield_overrides = VERSION_OVERRIDES
  readonly_fields = ['slug']
  list_display = ['name', 'filename']
  exclude = ('slug',)

class AnsiblePlaybookAdmin(admin.ModelAdmin):
  model = AnsiblePlaybook
  formfield_overrides = VERSION_OVERRIDES
  readonly_fields = ['slug']
  list_display = ['name', 'filename', 'scriptType']
  exclude = ('slug',)

  
class AnsibleRoleAdmin(admin.ModelAdmin):
  model = AnsibleRole
  formfield_overrides = VERSION_OVERRIDES
  readonly_fields = ['slug']
  list_display = ['name', 'roleurl', 'scriptType']
  exclude = ('slug',)

class AnsibleCollectionAdmin(admin.ModelAdmin):
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
