import sys
import traceback
from django.contrib import admin, messages
from django.forms import BaseInlineFormSet
from django.utils.html import mark_safe
from jobqueue.models import JobModule, JobStatus, Job
from django import forms
from django.urls import reverse
from django.db.models.query import QuerySet
from django.db.models import F

from django.shortcuts import render
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from scripts.models import Script
from common.rendered_config import RenderedConfigAdminMixin
import pyipmi
import pyipmi.interfaces
from systems.bootdev import bootdev_failed, set_pxe_bootdev
from func_timeout import func_timeout, FunctionTimedOut

from .models import (
  System,
  SystemBMC,
  SystemBMCForm,
  SystemGroup,
  NetworkInterface,
  SystemImage,
  SystemModel,
  NADSSystem,
  SystemLocation,
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
        }

class NetworkInterfaceInlineFormset(BaseInlineFormSet):
  
  def __init__(self, *args, **kwargs):
    super(NetworkInterfaceInlineFormset, self).__init__(*args, **kwargs)
    for form in self.forms:
      
      if 'switch_port' in form.initial:
        form.fields['switch_port'].queryset = form.fields['switch_port'].queryset.filter(networkinterface=None) | form.fields['switch_port'].queryset.filter(id=form.initial['switch_port'])
      else:
        form.fields['switch_port'].queryset = form.fields['switch_port'].queryset.filter(networkinterface=None)

  def clean(self):
    super().clean()
    bootable = [form for form in self.forms
                if getattr(form, 'cleaned_data', {}).get('bootable') and not form.cleaned_data.get('DELETE')]
    if len(bootable) > 1:
      raise ValidationError("Only one network interface can be bootable.")
  

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
  exclude = ('hostname',)

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
    except ValueError:
      ipv4idx = 0

    fields.insert(ipv4idx + 1, 'ipv6ll') #can also use insert
    fields.insert(ipv4idx + 2, 'ipv6gua')
    return fields
  

class BMCInline(admin.StackedInline):
  model = SystemBMC
  extra = 1
  max_num=1 
  list_display = ['id', 'ipaddress']
  list_display_links = ['id', 'ipaddress']
  readonly_fields = ['ipv6ll']
  verbose_name="System BMC"
  verbose_name_plural="System BMCs"
  form = SystemBMCForm
  def get_formset(self, request, obj, **kwargs):
    formset =  super().get_formset(request, obj, **kwargs)
    queryset = formset.form.base_fields['switch_port'].queryset
    queryset = queryset.select_related('switch', 'networks')
    formset.form.base_fields['switch_port'].queryset = queryset
    return formset


def warn_boot_disk_problems(modeladmin, request, systems):
  """ Warn about stateful systems the installer would refuse.  It's only a
  warning: layouts and partitions are often added after the system (#361). """
  for system in systems:
    problem = system.boot_disk_problem()
    if problem is not None:
      modeladmin.message_user(request, f"{problem}  PXE Boot will refuse it until that's fixed.", level=messages.WARNING)


def warn_duplicate_ip_assignments(modeladmin, request, systems):
  """ Warn when a NIC's IP address is already assigned to another system's NIC (#373).
  It's only a warning: the DB doesn't enforce a unique IP, and some duplicates
  (e.g. a floating/VIP address) are intentional. """
  for system in systems:
    for iface in NetworkInterface.objects.filter(system=system).exclude(ipaddress=None):
      conflict = NetworkInterface.objects.filter(ipaddress=iface.ipaddress) \
        .exclude(system=system).select_related('system').first()
      if conflict is not None:
        modeladmin.message_user(
          request,
          f"IP address {iface.ipaddress} is already in use by {conflict.system.hostname} "
          f"(interface {conflict.name}).",
          level=messages.WARNING,
        )


class SystemAdmin(RenderedConfigAdminMixin, admin.ModelAdmin):
  actions = [ 'bulk_update', 'sys_on', 'sys_off', 'sys_cycle', 'sys_pxe', 'sys_pxe_efi']

  inlines = [ NetworkInterfaceInline, BMCInline]
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
        'provision',
        'disks',
        'systemimage',
        'systemmodel',
        'systemgroups',
        'location',
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

  def save_related(self, request, form, formsets, change):
    # disks is a many-to-many, saved here after the system itself.
    super().save_related(request, form, formsets, change)
    warn_boot_disk_problems(self, request, [form.instance])
    warn_duplicate_ip_assignments(self, request, [form.instance])

  def response_change(self, request, obj):
        # Check if our custom button was clicked
        if "_copy_to_new" in request.POST:
            # 1. Duplicate the object by clearing its primary key
            obj.pk = None
            
            obj.save()
            
            # 2. Notify the user
            self.message_user(request, "Object copied successfully to a new record.")
            
            # 3. Redirect to the newly created object's edit page
            opts = self.model._meta
            redirect_url = reverse(
                f"admin:{opts.app_label}_{opts.model_name}_change", 
                args=[obj.pk]
            )
            return HttpResponseRedirect(redirect_url)
            
        # Fall back to default behavior if the button wasn't clicked
        return super().response_change(request, obj)
  def getBMClink(self,obj):
    bmcq = SystemBMC.objects.filter(system=obj)
    if bmcq is not None:
      if type(bmcq) is QuerySet and len(bmcq) != 0:
        bmcq = bmcq[0]
        return mark_safe(f"<a href=\"http://{bmcq.ipaddress}\" target=\"_blank\">http://{bmcq.ipaddress}</a>")
    return mark_safe("N/A")
  def getPower(self, obj):
     return mark_safe(f"<img src=\"/systems/{obj.id}/?powerstate\" width=\"32\" height=\"32\" />")
  def getMacs(self, obj):

    query = NetworkInterface.objects.filter(system=obj).select_related('switch_port')
    netstr = ""
    for netinf in query:
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
           print(f"Error: Unable to find bmc for {system.hostname}")
           continue
        mybmc = mybmc[0]
        try:
          func_timeout(1, self._doPowerCmd, [mybmc, "cycle"])
        except FunctionTimedOut:
           print(f"Error: {system.hostname} bmc timeout (ip: {mybmc.ipaddress})")
  @admin.action(description="Power On")
  def sys_on(self, request, queryset):
     for system in queryset:
        mybmc = SystemBMC.objects.all().filter(system=system.id)
        if len(mybmc) != 1:
           print(f"Error: Unable to find bmc for {system.hostname}")
           continue
        mybmc = mybmc[0]
        try:
          func_timeout(1, self._doPowerCmd, [mybmc, "on"])
        except FunctionTimedOut:
           print(f"Error: {system.hostname} bmc timeout (ip: {mybmc.ipaddress})")
  @admin.action(description="Power Off")
  def sys_off(self, request, queryset):
     for system in queryset:
        mybmc = SystemBMC.objects.all().filter(system=system.id)
        if len(mybmc) != 1:
           print(f"Error: Unable to find bmc for {system.hostname}")
           continue
        mybmc = mybmc[0]
        try:
          func_timeout(1, self._doPowerCmd, [mybmc, "off"])
        except FunctionTimedOut:
           print(f"Error: {system.hostname} bmc timeout (ip: {mybmc.ipaddress})")
  @admin.action(description="Boot to PXE (Legacy)")
  def sys_pxe(self, request, queryset):
     self._pxeBoot(request, queryset, "pxe")
  @admin.action(description="Boot to PXE (EFI)")
  def sys_pxe_efi(self, request, queryset):
     self._pxeBoot(request, queryset, "pxeefi")

  def _pxeBoot(self, request, queryset, action):
     for system in queryset: 
        mybmc = SystemBMC.objects.all().filter(system=system.id)
        if len(mybmc) != 1:
           print(f"Error: Unable to find bmc for {system.hostname}")
           continue
        mybmc = mybmc[0]
        was_provisioning = system.provision
        if not system.enable_provisioning():
           self._cantProvision(request, system)
           continue
        try:
          result = func_timeout(5, self._doPowerCmd, [mybmc, action])
        except FunctionTimedOut:
           print(f"Error: {system.hostname} bmc timeout (ip: {mybmc.ipaddress})")
           self.message_user(request, f"{system.hostname}: the BMC ({mybmc.ipaddress}) timed out; it may not have been reset.", level=messages.ERROR)
           continue
        if bootdev_failed(result):
           # nothing was reset, so nothing changes (#311).
           if system.provision != was_provisioning:
              system.provision = was_provisioning
              system.save()
           self.message_user(request, f"{system.hostname}: {result['details']}", level=messages.ERROR)
        else:
           self.message_user(request, f"{system.hostname}: set to PXE boot and reset.", level=messages.SUCCESS)
  
  def _cantProvision(self, request, system):
    self.message_user(request, f"{system.provisioning_problem()}  It was not reset.", level=messages.ERROR)

  def _doPowerCmd(self, bmc, action="on"):
    print(f"Bmc: {bmc.ipaddress}, user: {bmc.username}, action: {action}")

       
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
        if action == "pxe" or  action == "pxeefi":
          # don't reset the node into its old OS when the boot device
          # wasn't set (#311).  The PXE actions give this call 5 s in all.
          failed = set_pxe_bootdev(bmc, efi=(action == "pxeefi"), timeout=4)
          if failed:
            return failed
          # force a reset
          action = "reset"
          # make sure we are powered on
          try: 
             print("Issue power up... ")
             ipmi.chassis_control_power_up()
          except Exception:
             pass
        
        print(f"IPMI Power Action{action}")     
        if action=="on":
            print("Issue power up... ")
            ipmi.chassis_control_power_up()
        elif action=="off":
            print("Issue power off... ")
            ipmi.chassis_control_power_down()
        elif action=="reset":
            try:
              print("Issue hard_reset ... ")
              ipmi.chassis_control_hard_reset()
            except Exception:
              print("Issue power cycle ... ")

              ipmi.chassis_control_power_cycle()
              
        elif action=="cycle":
            print("Issue power cycle ... ")
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
    fields = ['systemimage','systemmodel','stateful','provision','prov_interface','initial_mods', 'systemgroups', 'disks', 'location']
    def remove_fields(form):
        for field in list(form.base_fields.keys()):
            if field not in fields:
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

            form.full_clean()  # populate cleaned_data; form.is_valid() is not used here
            fieldsUpdated = False
            for field_name in fields:
              
              if f"update_{field_name}" not in request.POST:
                 continue
              cleaned_field_data = form.cleaned_data[field_name]
              is_m2m = self.model._meta.get_field(field_name).many_to_many
              for item in queryset.all():
                  if is_m2m:
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
                  if is_m2m:
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
            warn_boot_disk_problems(self, request, queryset.all())
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
  list_display = ['mac', 'vendor', 'model', 'switch', 'port', 'serial']
  readonly_fields = ['mac', 'vendor', 'model', 'switch', 'port', 'serial']
  def has_add_permission(self,request):
    return False

class SystemLocationAdmin(admin.ModelAdmin):
   def get_list_display(self, request):
        return [field.name for field in self.model._meta.concrete_fields]

@admin.action(description="Mark images as needing rebuild")
def mark_rebuild(modeladmin, request, queryset):
  queryset.update(needs_rebuild=True)
  try:
      JobType = JobModule.objects.get(slug='image-update')
  except JobModule.DoesNotExist:
      # do nothing if the jobtype isn't defined.
      return

  for instance in queryset:
    # create a new image-update job.
    params = { 'imageId': instance.slug}
    Job.objects.create( name=JobType.name,
        module=JobType,
        status=JobStatus.objects.get(pk=1),
        params = params,
    )

    # Increment version number and clear out jobservers field.
    # update() saves the version without firing UpdateSystemImages, which
    # would queue a second job and clear needs_rebuild.
    instance.jobservers.clear()
    SystemImage.objects.filter(pk=instance.pk).update(version=F('version') + 1)

class SystemImageAdmin(RenderedConfigAdminMixin, admin.ModelAdmin):
  list_display = ['slug', 'name', 'osdistro', 'version', 'registered_jobservers']
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
  def get_queryset(self, request):
    return super().get_queryset(request).select_related('osdistro')

  def registered_jobservers(self, obj):
    return ", ".join([jm.name for jm in obj.jobservers.all()])
  registered_jobservers.short_description = 'Registered Job Servers'

  def get_form(self, request, obj, **kwargs):
    form = super(SystemImageAdmin, self).get_form(request, obj, **kwargs)
    form.base_fields['scripts'].queryset = Script.objects.exclude(scriptType='post-boot')
    # #424: the name is part of how the image's identity (slug) is derived,
    # so changing it on an existing image makes a new copy rather than
    # renaming this one in place.
    form.base_fields['name'].help_text = "Changing this on an existing image creates a new copy of it; it doesn't rename this one in place."
    return form
  
  
admin.site.register(SystemImage, SystemImageAdmin)
admin.site.register(SystemGroup, SystemGroupAdmin)
admin.site.register(System, SystemAdmin)
admin.site.register(SystemModel, SystemModelAdmin)
admin.site.register(NADSSystem, NADSAdmin)
admin.site.register(SystemLocation, SystemLocationAdmin)
