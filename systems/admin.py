from csv import list_dialects
from django.contrib import admin
from django.contrib.contenttypes.admin import GenericStackedInline

from .models import (
  System,
  SystemGroup,
  NetworkInterface,
  SystemImage,
)


class NetworkInterfaceInline(admin.StackedInline):
  model = NetworkInterface
  extra=1
  list_display = ['id', 'name']
  list_display_links = ['id', 'name']
  verbose_name="Network Interfaces"
  verbose_name_plural="Network Interfaces"



class SystemAdmin(admin.ModelAdmin):
  inlines = [NetworkInterfaceInline]
  list_display = ['id', 'hostname']
  readonly_fields = ['timestamp', 'updated', 'created_by']
  list_display_links = ['id', 'hostname']
  fieldsets = (
    (None, {
      'fields': (
        'hostname',
        'created_by',
        'timestamp',
        'updated',
        'systemgroups',
        'scripts',
        'config_params',
      )
    }),
    ('OS Management', {
      'fields': ('osdistro','osrepos')
    }
    ),
  )

class SystemGroupAdmin(admin.ModelAdmin):
  list_display = ['id', 'name']
  list_display_links = ['id', 'name']

class SystemImageAdmin(admin.ModelAdmin):
  list_display = ['slug', 'name', 'version', 'registered_jobservers']
  readonly_fields = ['timestamp', 'updated', 'created_by',  'jobservers']
  list_display_links = ['slug', 'name']
  fieldsets = (
    (None, {
      'fields': (
        'name',
        'created_by',
        'timestamp',
        'updated',
        'version',
        'jobservers',
        'systemgroups',
        'scripts',
        'config_params',
        'needs_rebuild',
      )
    }),
    ('OS Management', {
      'fields': ('osdistro','osrepos')
    }
    ),
  )
  def registered_jobservers(self, obj):
    return ", ".join([jm.name for jm in obj.jobservers.all()])
  registered_jobservers.short_description = 'Registered Job Servers'
  
  
admin.site.register(SystemImage, SystemImageAdmin)
admin.site.register(SystemGroup, SystemGroupAdmin)
admin.site.register(System, SystemAdmin)
