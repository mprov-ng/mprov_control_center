from django.contrib import admin
from django.dispatch import receiver
from .models import Script, ScriptType, AnsiblePlaybook, AnsibleRole, AnsibleCollection, File

class ScriptAdmin(admin.ModelAdmin):
  model = Script
  readonly_fields = ['slug']
  list_display = ['name', 'filename', 'scriptType']
  exclude = ('slug',)
  fields = ('name', 'filename', 'content', 'scriptType', 'version', 'dependsOn')

  def get_form(self, request, obj=None, **kwargs):
    form = super().get_form(request, obj, **kwargs)
    if obj and not obj.content:  # If editing an existing object and content is empty
      obj.content = obj.get_content_from_file()
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
