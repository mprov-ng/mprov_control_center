from csv import list_dialects
import sys
from tabnanny import verbose
import traceback
from django.contrib import admin
from django.contrib.contenttypes.admin import GenericStackedInline
from django.forms import BaseInlineFormSet
from django.utils.html import mark_safe
from networks.models import SwitchPort
from django.utils.text import slugify
from jobqueue.models import JobModule, JobStatus, Job
from django import forms

from django.template.response import TemplateResponse
from django.contrib.admin.utils import model_ngettext
from django.contrib.admin import helpers
from django.shortcuts import render
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.db.models import ManyToManyField
from scripts.models import Script
import pyipmi
import pyipmi.interfaces
from func_timeout import func_timeout, FunctionTimedOut
import subprocess

from .models import (
  System,
  SystemBMC,
  SystemBMCForm,
  SystemGroup,
  NetworkInterface,
  SystemImage,
  SystemModel,
  NADSSystem,
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
  actions = [ 'bulk_update', 'sys_on', 'sys_off', 'sys_cycle', 'sys_pxe']
  
  inlines = [ NetworkInterfaceInline, BMCInLine]
  list_display = ['id', 'getPower', 'hostname', 'getMacs', 'getSwitchPort', 'getBMClink']
  readonly_fields = ['timestamp', 'updated', 'created_by']
  list_display_links = ['id', 'hostname']
  list_per_page = 25
  search_fields = ['hostname']
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
        'ansiblecollections',
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
  def getBMClink(self,obj):
    bmcq = SystemBMC.objects.filter(system=obj)
    
    if bmcq is not None:
      bmcq = bmcq[0]
      return mark_safe(f"<a href=\"http://{bmcq.ipaddress}\" target=\"_blank\">http://{bmcq.ipaddress}</a>")
    return mark_safe("N/A")
  def getPower(self, obj):
     return mark_safe(f"<img src=\"/systems/{obj.id}/?powerstate\" width=\"32\" height=\"32\" />")
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
  getPower.short_description = "Status"
  getBMClink.short_description = "BMC Link"

  @admin.action(description="Power Cycle")
  def sys_cycle(self, request, queryset):
     for system in queryset:
        mybmc = SystemBMC.objects.all().filter(system=system.id)
        if len(mybmc) != 1:
           print(f"Error: Unable to find bmc for {system.name}")
           continue
        mybmc = mybmc[0]
        try:
          func_timeout(1, self._doPowerCmd, [mybmc, "cycle"])
        except FunctionTimedOut:
           print(f"Error: {system.name} bmc timeout (ip: {mybmc.ipaddress})")
  @admin.action(description="Power On")
  def sys_on(self, request, queryset):
     for system in queryset:
        mybmc = SystemBMC.objects.all().filter(system=system.id)
        if len(mybmc) != 1:
           print(f"Error: Unable to find bmc for {system.name}")
           continue
        mybmc = mybmc[0]
        try:
          func_timeout(1, self._doPowerCmd, [mybmc, "on"])
        except FunctionTimedOut:
           print(f"Error: {system.name} bmc timeout (ip: {mybmc.ipaddress})")
  @admin.action(description="Power Off")
  def sys_off(self, request, queryset):
     for system in queryset:
        mybmc = SystemBMC.objects.all().filter(system=system.id)
        if len(mybmc) != 1:
           print(f"Error: Unable to find bmc for {system.name}")
           continue
        mybmc = mybmc[0]
        try:
          func_timeout(1, self._doPowerCmd, [mybmc, "off"])
        except FunctionTimedOut:
           print(f"Error: {system.name} bmc timeout (ip: {mybmc.ipaddress})")
  @admin.action(description="Boot to PXE")
  def sys_pxe(self, request, queryset):
     for system in queryset: 
        mybmc = SystemBMC.objects.all().filter(system=system.id)
        if len(mybmc) != 1:
           print(f"Error: Unable to find bmc for {system.name}")
           continue
        mybmc = mybmc[0]
        try:
          func_timeout(5, self._doPowerCmd, [mybmc, "pxe"])
        except FunctionTimedOut:
           print(f"Error: {system.name} bmc timeout (ip: {mybmc.ipaddress})")
  
  
  def _doPowerCmd(self, bmc, action="on"):
    print(f"Bmc: {bmc.ipaddress}, user: {bmc.username}, pass: {bmc.password}, action: {action}")

       
    interface = pyipmi.interfaces.create_interface('rmcp', slave_address=0x81,
                                            host_target_address=0x20,
                                            keep_alive_interval=0)
    interface = pyipmi.interfaces.create_interface('ipmitool', interface_type='lanplus')
    ipmi = pyipmi.create_connection(interface)
    ipmi.session.set_session_type_rmcp(bmc.ipaddress, 623)
    ipmi.session.set_auth_type_user(bmc.username, bmc.password)
    
    try:
        ipmi.session.establish()
        ipmi.target = pyipmi.Target(ipmb_address=0x20)
        if action == "pxe":
          # XXX: bootdev is not implemented in python-ipmi(pyipmi)
          # so we will need to issue a raw ipmitool command.
          ipmitool_cmd = f"/usr/bin/ipmitool -Ilanplus -U{bmc.username} -P{bmc.password} -H{bmc.ipaddress} chassis bootdev pxe"
          subprocess.run(args=ipmitool_cmd.split())
          # force a reset
          action = "reset"
          # make sure we are powered on
          try: 
             ipmi.chassis_control_power_up()
          except:
             pass
        

        if action=="on":
            ipmi.chassis_control_power_up()
        elif action=="off":
            ipmi.chassis_control_power_down()
        elif action=="reset":
            try:
              ipmi.chassis_control_hard_reset()
            except:
              ipmi.chassis_control_power_cycle()
              
        elif action=="cycle":
            ipmi.chassis_control_power_cycle()
        elif action=="status":
            
            chassis = ipmi.get_chassis_status()
          
            print({'status': 200, 'chassis_status': chassis.power_on})
    except Exception as e:
        print({'details': f"Exception {e}", "status": "400", 'chassis_status': 'unknown'})
        exc_type, exc_value, exc_traceback = sys.exc_info()

        traceback.print_tb(exc_traceback)
        
  
  @admin.action(description="Update fields on multiple systems")
  def bulk_update(self, request, queryset):
    # fields to allow multiple updates to.
    fields = ['systemimage','systemmodel','stateful','prov_interface','initial_mods', 'systemgroups', 'disks']
    def remove_fields(form):
        for field in list(form.base_fields.keys()):
            if field  not in fields:
                del form.base_fields[field]
        return form

    form_class = remove_fields(self.get_form(request))

    if request.method == 'POST':
        form = form_class()

        # the view is already called via POST from the django admin changelist
        # here we have to distinguish between just showing the intermediary view via post
        # and actually confirming the bulk edits
        # for this there is a hidden field 'form-post' in the html template
        if 'form-post' in request.POST:
            form = form_class(request.POST)
            has_batch_errors = False

            form.full_clean()  # form.is_valid() will not work well because <WorkEntry: None>
            fieldsUpdated = False
            for field_name in fields:
              
              if f"update_{field_name}" not in request.POST:
                 continue
              cleaned_field_data = form.cleaned_data[field_name]
              for item in queryset.all():
                  fieldCheck = getattr(item, field_name)
                  fieldCheck = fieldCheck
                  print(fieldCheck.__class__.__name__)
                  if fieldCheck.__class__.__name__ == "ManyRelatedManager": 
                     item.clean()
                  else: 
                    try:
                        setattr(item, field_name, cleaned_field_data)
                        item.clean()
                    except ValidationError as e:
                        form.add_error(None, e)
                        has_batch_errors = True

              if has_batch_errors:
                  return render(
                      request,
                      'admin/system_bulk_change_form.html',
                      context={
                          **self.admin_site.each_context(request),
                          'adminform': form,
                          'items': queryset,
                          'media': self.media,
                          'opts': self.model._meta,
                      }
                  )

              for item in queryset.all():
                  if fieldCheck.__class__.__name__ == "ManyRelatedManager": 
                     m2mfield = getattr(item, field_name)
                     m2mfield.set(cleaned_field_data)
                     item.save()
                  else: 
                    try: 
                      setattr(item, field_name, cleaned_field_data)
                      item.save()
                    except ValidationError as e:
                      form.add_error(None, e)
                      return render(
                          request,
                          'admin/system_bulk_change_form.html',
                          context={
                              **self.admin_site.each_context(request),
                              'adminform': form,
                              'items': queryset,
                              'media': self.media,
                              'opts': self.model._meta,
                          }
                      )
                  fieldsUpdated=True
            if fieldsUpdated is False:
              self.message_user(request, "No fields selected to update.")
              return render(
                 request,
                 'admin/system_bulk_change_form.html',
                  context={
                      **self.admin_site.each_context(request),
                      'adminform': form,
                      'items': queryset,
                      'media': self.media,
                      'opts': self.model._meta,
                  }
              )
            self.message_user(
                request,
                "Changed fields on {} items".format(
                    queryset.count(),
                )
            )
            return HttpResponseRedirect(request.get_full_path())

        return render(
            request,
            'admin/system_bulk_change_form.html',
            context={
                **self.admin_site.each_context(request),
                'adminform': form,
                'items': queryset,
                'media': self.media,
                'opts': self.model._meta,
            }
        )
    # objects_name = model_ngettext(queryset)
    # context = {
    #   **self.admin_site.each_context(request),
    #   'title': 'Update Multiple',
    #   'objects_name': str(objects_name),
    #   'queryset': queryset,
    #   'opts': self.model._meta,
    #   'action_checkbox_name': helpers.ACTION_CHECKBOX_NAME,
    #   'media': self.media,
    # }
    # return TemplateResponse(request, "admin/system_bulk_change_form.html", context)
    # pass


class SystemGroupAdmin(admin.ModelAdmin):
  list_display = ['id', 'name']
  list_display_links = ['id', 'name']

class SystemModelAdmin(admin.ModelAdmin):
  list_display = ['slug', 'vendor', 'name']
  verbose_name = "System Models"
  verbose_name_plural = "System Models"
  exclude = ['slug']

class NADSAdmin(admin.ModelAdmin):
  verbose_name = "N.A.D.S Discovered"
  verbose_name_plural = "N.A.D.S Discovered"
  list_display = ['mac', 'vendor', 'model', 'switch', 'port']
  readonly_fields = ['mac', 'vendor', 'model', 'switch', 'port']
  def has_add_permission(self,request):
    return False

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
        'ansiblecollections',
        'ansibleplaybooks',
        'ansibleroles',
        'customIPXE',
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

  def get_form(self, request, obj, **kwargs):
    form = super(SystemImageAdmin, self).get_form(request, obj, **kwargs)
    form.base_fields['scripts'].queryset = Script.objects.exclude(scriptType='post-boot')
    return form
  
  
admin.site.register(SystemImage, SystemImageAdmin)
admin.site.register(SystemGroup, SystemGroupAdmin)
admin.site.register(System, SystemAdmin)
admin.site.register(SystemModel, SystemModelAdmin)
admin.site.register(NADSSystem, NADSAdmin)
