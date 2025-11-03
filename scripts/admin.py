from django.contrib import admin
from django.dispatch import receiver
from django.conf import settings
from .models import Script, ScriptType, AnsiblePlaybook, AnsibleRole, AnsibleCollection, File
from djangocodemirror.widgets import CodeMirrorAdminWidget
import os

class ScriptAdmin(admin.ModelAdmin):
  model = Script
  readonly_fields = ['slug']
  list_display = ['name', 'filename', 'scriptType']
  exclude = ('slug',)
  change_form_template ='admin/scripts_change_form.html'

  def get_form(self, request, obj=None, **kwargs):
      """
      Override to populate content field with file contents when editing existing scripts
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
  readonly_fields = ['slug']
  list_display = ['name', 'filename']
  exclude = ('slug',)

class AnsiblePlaybookAdmin(admin.ModelAdmin):
  model = AnsiblePlaybook
  readonly_fields = ['slug']
  list_display = ['name', 'filename', 'scriptType']
  exclude = ('slug',)

  
class AnsibleRoleAdmin(admin.ModelAdmin):
  model = AnsibleRole
  readonly_fields = ['slug']
  list_display = ['name', 'roleurl', 'scriptType']
  exclude = ('slug',)

class AnsibleCollectionAdmin(admin.ModelAdmin):
  model = AnsibleCollection
  readonly_fields = ['slug']
  list_display = ['name', 'collectionurl', 'scriptType']
  exclude = ('slug',)


class ScriptTypeAdmin(admin.ModelAdmin):
  model = ScriptType
  list_display = ['name']


admin.site.register(File, FileAdmin)
admin.site.register(AnsiblePlaybook, AnsiblePlaybookAdmin)
admin.site.register(AnsibleRole, AnsibleRoleAdmin)
admin.site.register(AnsibleCollection, AnsibleCollectionAdmin)
admin.site.register(Script, ScriptAdmin)
