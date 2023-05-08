from csv import list_dialects
from tabnanny import verbose
from django.contrib import admin
from django.contrib.contenttypes.admin import GenericStackedInline
from django.forms import BaseInlineFormSet
from django.utils.html import mark_safe
from networks.models import SwitchPort
from django.utils.text import slugify
from jobqueue.models import JobModule, JobStatus, Job
from django import forms


from .models import (
  System,
  SystemBMC,
  SystemBMCForm,
  SystemGroup,
  NetworkInterface,
  SystemImage,
  SystemModel,
)

class NetForm(forms.ModelForm):
    class Meta:
        widgets = {
            'name': forms.TextInput(attrs={
              'size': '5',
              'class': 'vTextField',
              'style': 'width: 5em;',
            }),
            'bootable': forms.CheckboxInput(attrs={
              'style': 'width: 5em;',
            }),
            'ipaddress': forms.TextInput(attrs={
              'style': 'width: 7em;',
              'class': 'vTextField',
            }),
        }

class NetworkInterfaceInlineFormset(BaseInlineFormSet):
  
  def __init__(self, *args, **kwargs):
    super(NetworkInterfaceInlineFormset, self).__init__(*args, **kwargs)
    for form in self.forms:
      
      if 'switch_port' in form.initial:
        form.fields['switch_port'].queryset = form.fields['switch_port'].queryset.filter(networkinterface=None) | form.fields['switch_port'].queryset.filter(id=form.initial['switch_port'])
      else:
        form.fields['switch_port'].queryset = form.fields['switch_port'].queryset.filter(networkinterface=None)
  

class NetworkInterfaceInline(admin.StackedInline):
  model = NetworkInterface
  extra=1
  formset = NetworkInterfaceInlineFormset
  form = NetForm
  list_display = ['id', 'name']
  list_display_links = ['id', 'name']
  verbose_name="Network Interfaces"
  verbose_name_plural="Network Interfaces"
  readonly_fields = ['ipv6ll', 'ipv6gua']

  def get_formset(self, request, obj, **kwargs):
    formset =  super().get_formset(request, obj, **kwargs)
    queryset = formset.form.base_fields['switch_port'].queryset
    queryset = queryset.select_related('switch', 'networks')
    formset.form.base_fields['switch_port'].queryset = queryset
    return formset

  
  def get_fields (self, request, obj=None, **kwargs):
    fields = super().get_fields(request, obj, **kwargs)
    fields.remove('ipv6ll')
    fields.remove('ipv6gua')
    try:
      ipv4idx = fields.index('ipaddress')
    except:
      ipv4idx = 0

    fields.insert(ipv4idx + 1, 'ipv6ll') #can also use insert
    fields.insert(ipv4idx + 2, 'ipv6gua')
    return fields
  

class BMCInLine(admin.StackedInline):
  model = SystemBMC
  extra = 1
  max_num=1 
  list_display = ['id', 'ipaddress']
  list_display_links = ['id', 'ipaddress']
  readonly_fields = ['ipv6ll']
  verbose_name="System BMC"
  verbose_name="System BMCs"
  form = SystemBMCForm
  def get_formset(self, request, obj, **kwargs):
    formset =  super().get_formset(request, obj, **kwargs)
    queryset = formset.form.base_fields['switch_port'].queryset
    queryset = queryset.select_related('switch', 'networks')
    formset.form.base_fields['switch_port'].queryset = queryset
    return formset


class SystemAdmin(admin.ModelAdmin):
  inlines = [ NetworkInterfaceInline, BMCInLine]
  list_display = ['id', 'hostname', 'getMacs', 'getSwitchPort']
  readonly_fields = ['timestamp', 'updated', 'created_by']
  list_display_links = ['id', 'hostname']
  change_form_template ='admin/system_change_form.html'
  fieldsets = (
    (None, {
      'fields': (
        'hostname',
        'created_by',
        'timestamp',
        'updated',
        
      )
    }),
    ('System Parameters', {
      'fields': [
        'stateful',
        'disks',
        'systemimage',
        'systemmodel',
        'systemgroups',
        'scripts',
        'ansibleplaybooks',
        'ansibleroles',
        'config_params',
        'install_kernel_cmdline',
        'tmpfs_root_size',
        'initial_mods',
        'prov_interface',
        ]
    }
    ),
  )
  def getMacs(self, obj):

    query = NetworkInterface.objects.filter(system=obj).select_related('switch_port')
    netstr = ""
    for netinf in query:
      # print(netinf)
      netstr += netinf.name + ": [" + str(netinf.mac) + "]<br />"
    return mark_safe(netstr)

  def getSwitchPort(self, obj):
    query = NetworkInterface.objects.filter(system=obj).select_related('switch_port')
    portstr = ""
    for netinf in query:
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
  exclude = ['slug']


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
  exclude = ('slug', )
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
        'ansibleplaybooks',
        'ansibleroles',
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