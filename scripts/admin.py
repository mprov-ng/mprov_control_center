from django.contrib import admin
from django.dispatch import receiver
from .models import Script, ScriptType

class ScriptAdmin(admin.ModelAdmin):
  model = Script
  readonly_fields = ['slug']
  list_display = ['name', 'filename', 'scriptType']
  exclude = ('slug',)


class ScriptTypeAdmin(admin.ModelAdmin):
  model = ScriptType
  list_display = ['name']

admin.site.register(Script, ScriptAdmin)

