from csv import list_dialects
from tabnanny import verbose
from django.contrib import admin
from django.contrib.contenttypes.admin import GenericStackedInline
from django.forms import BaseInlineFormSet
from django.utils.html import mark_safe
from networks.models import SwitchPort
from django.utils.text import slugify
from jobqueue.models import JobModule, JobStatus, Job

from .models import (
  System,
  SystemBMC,
  SystemGroup,
  NetworkInterface,
  SystemImage,
  SystemModel,
)

class NetworkInterfaceInlineFormset(BaseInlineFormSet):
  def __init__(self, *args, **kwargs):
    super(NetworkInterfaceInlineFormset, self).__init__(*args, **kwargs)
    # print( SwitchPort.objects.filter(networkinterface=None) )
   
    # for form in self.forms:
    #   form.fields['switch_port'].queryset = SwitchPort.objects.filter(networkinterface=None)
    

class NetworkInterfaceInline(admin.TabularInline):
  model = NetworkInterface
  extra=1
  formset = NetworkInterfaceInlineFormset

  list_display = ['id', 'name']
  list_display_links = ['id', 'name']
  verbose_name="Network Interfaces"
  verbose_name_plural="Network Interfaces"
  # def get_form(self, request, obj=None, **kwargs):
  #   form = super(NetworkInterfaceInline, self).get_form(request, obj, **kwargs)
  #   print(SwitchPort.objects.filter(networkinterface=None))
  #   form.base_fields['switch_port'].queryset = SwitchPort.objects.filter(networkinterface=None)
  #   return form

  # def render_change_form(self, request, context, *args, **kwargs):
  #   context['adminform'].form.fields['switch_port'].queryset = SwitchPort.objects.filter(networkinterface=None)
  #   return super(NetworkInterfaceInline, self).render_change_form(*args, **kwargs)
  #   #self.fields['switch_port'] = 

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
    ('System Parameters', {
      'fields': ['systemimage','systemmodel']
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

class SystemModelAdmin(admin.ModelAdmin):
  list_display = ['slug', 'vendor', 'name']
  verbose_name = "System Models"
  verbose_name_plural = "System Models"
  readonly_fields = ['slug']

@admin.action(description="Mark images as needing rebuild.")
def mark_rebuild(modeladmin, request, queryset):
  queryset.update(needs_rebuild=True)
  for instance in queryset:
    if not instance.needs_rebuild: 
      return
    instance.slug = slugify(instance.name)

    JobType = None
    try:
        JobType = JobModule.objects.get(slug='image-update')
    except:
        JobType = None
    # print(str(JobType) + " post")

    # get the jobtype, do nothing if it's not defined.
    if JobType is not None:

        # save a new job, if one doesn't already exist.
        params = { 'imageId': instance.slug}
        Job.objects.create( name=JobType.name, 
            module=JobType, 
            status=JobStatus.objects.get(pk=1), 
            params = params,
        )

        # TODO: Increment version number and clear out jobservers field.
        instance.jobservers.clear()
        instance.version = instance.version + 1

class SystemImageAdmin(admin.ModelAdmin):
  list_display = ['slug', 'name', 'version', 'registered_jobservers']
  readonly_fields = ['timestamp', 'updated', 'created_by',  'jobservers']
  list_display_links = ['slug', 'name']
  actions= [mark_rebuild]
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
admin.site.register(SystemModel, SystemModelAdmin)