from csv import list_dialects
from tabnanny import verbose
from django.contrib import admin
from django.contrib.contenttypes.admin import GenericStackedInline
from django.utils.html import mark_safe

from .models import (
  System,
  SystemBMC,
  SystemGroup,
  NetworkInterface,
  SystemImage,
)


class NetworkInterfaceInline(admin.TabularInline):
  model = NetworkInterface
  extra=1
  list_display = ['id', 'name']
  list_display_links = ['id', 'name']
  verbose_name="Network Interfaces"
  verbose_name_plural="Network Interfaces"

class BMCInLine(admin.StackedInline):
  model = SystemBMC
  extra = 1
  list_display = ['id', 'ipaddress']
  list_display_links = ['id', 'ipaddress']
  verbose_name="System BMC"
  verbose_name="System BMCs"


class SystemAdmin(admin.ModelAdmin):
  inlines = [NetworkInterfaceInline, BMCInLine]
  list_display = ['id', 'hostname', 'getMacs', 'getSwitchPort']
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
      'fields': ['systemimage',]
    }
    ),
  )
  def getMacs(self, obj):

    query = NetworkInterface.objects.all()
    query = query.filter(system=obj)
    netstr = ""
    for netinf in query.all():
      print(netinf)
      netstr += netinf.name + ": [" + str(netinf.mac) + "]<br />"
    return mark_safe(netstr)

  def getSwitchPort(self, obj):
    query = NetworkInterface.objects.all()
    query = query.filter(system=obj)
    portstr = ""
    for netinf in query.all():
      portstr += netinf.name + ": " + str(netinf.switch_port) + "<br />"
    return mark_safe(portstr)
  getSwitchPort.short_description = "Switch Ports"
  getMacs.short_description = 'Network\nInterfaces'

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
