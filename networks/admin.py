import ipaddress

from django.contrib import admin, messages
from django.shortcuts import render, redirect
from django.urls import path, reverse
from django.http import QueryDict
from django.utils.html import format_html, format_html_join
from systems.models import NetworkInterface, SystemBMC
from .models import Network, NetworkType, Switch, SwitchPort
from .utils import get_associated_objects, calculate_new_ips


class NetworkAdmin(admin.ModelAdmin):
  model = Network
  # Removing vlan for now.
  #list_display = ['slug', 'name', 'net_type', 'vlan', 'subnet', 'netmask']
  list_display = ['slug', 'name', 'net_type', 'subnet', 'netmask']
  readonly_fields = ['slug', 'network_summary']
  list_display_links = ['slug', 'name',]
  exclude = ('slug',)

  def get_fieldsets(self, request, obj=None):
      # jazzmin shows each fieldset as a tab; the summary only exists once the network does.
      fields = [f for f in self.get_fields(request, obj) if f != 'network_summary']
      fieldsets = [(None, {'fields': fields})]
      if obj is not None:
          fieldsets.append(('Network Summary', {'fields': ['network_summary']}))
      return fieldsets

  def get_object(self, request, object_id, from_field=None):
      obj = super().get_object(request, object_id, from_field)
      if obj is not None:
          # network_summary() only gets the object, so it carries the table's sort order.
          obj.summary_sort = request.GET.get('summary_sort', 'hostname')
      return obj

  @admin.display(description='Hosts on this network')
  def network_summary(self, obj):
      """ A table of the NICs and BMCs on this network, each linking to its system, sorted by hostname
      (then NIC name) or by IP address. """
      nics = NetworkInterface.objects.filter(network=obj).select_related('system', 'switch_port__switch')
      bmcs = SystemBMC.objects.filter(network=obj).select_related('system', 'switch_port__switch')
      rows = [(nic.system, 0, nic.name, nic.mac, nic.ipaddress, nic.switch_port, 'Yes' if nic.bootable else 'No')
              for nic in nics]
      rows += [(bmc.system, 1, format_html('<span class="badge bg-info">BMC</span>'), bmc.mac, bmc.ipaddress,
                bmc.switch_port, 'N/A') for bmc in bmcs]
      if not rows:
          return 'No systems on this network.'
      by_ip = getattr(obj, 'summary_sort', 'hostname') == 'ip'
      by_host = lambda r: (r[0].hostname, r[1], str(r[2]))
      if by_ip:
          # NICs without an IP go last.
          ip_key = lambda ip: (0, ipaddress.ip_address(ip).version, int(ipaddress.ip_address(ip))) if ip else (1, 0, 0)
          rows.sort(key=lambda r: (ip_key(r[4]),) + by_host(r))
      else:
          rows.sort(key=by_host)
      body = format_html_join('', '<tr><td><a href="{}">{}</a></td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>',
          ((reverse('admin:systems_system_change', args=[system.pk]), system.hostname, iface,
            mac or 'N/A', ip or 'N/A', port if port else 'N/A', bootable)
           for system, _, iface, mac, ip, port, bootable in rows))
      header = lambda key, label, active: format_html(
          '<a href="?summary_sort={}#network-summary-tab">{}</a>{}', key, label,
          format_html(' <i class="fas fa-sort-down"></i>') if active else '')
      return format_html('<table class="table table-sm table-striped"><thead><tr><th>{}</th><th>Interface</th>'
                         '<th>MAC Address</th><th>{}</th><th>Switch / Port</th><th>Bootable</th></tr></thead>'
                         '<tbody>{}</tbody></table>',
                         header('hostname', 'Hostname', not by_ip), header('ip', 'IP Address', by_ip), body)

  def get_urls(self):
      urls = super().get_urls()
      custom_urls = [
          path('<path:object_id>/update-with-confirmation/', 
               self.admin_site.admin_view(self.update_with_confirmation_view), 
               name='network_update_with_confirmation'),
      ]
      return custom_urls + urls

  def save_model(self, request, obj, form, change):
      # Check if this is a change operation and if subnet/netmask is being changed
      if change and ('subnet' in form.changed_data or 'netmask' in form.changed_data):
          # Get the original values from the database
          original_obj = Network.objects.get(pk=obj.pk)
          old_subnet = str(original_obj.subnet)
          old_netmask = str(original_obj.netmask)
          new_subnet = str(obj.subnet)
          new_netmask = str(obj.netmask)

          if old_subnet != new_subnet or old_netmask != new_netmask:
              # Store the form data in session for the confirmation view
              # Don't save the object yet - we'll do that after confirmation
              request.session['network_update_data'] = {
                  'object_id': str(obj.pk),
                  'form_data': dict(request.POST),
                  'old_subnet': old_subnet,
                  'old_netmask': old_netmask,
                  'new_subnet': new_subnet,
                  'new_netmask': new_netmask,
                  'changed_fields': list(form.changed_data),
              }
              # Set a flag to prevent the normal save
              request._network_update_confirmation_needed = True
              return
      
      # If no subnet/netmask change, proceed with normal save
      super().save_model(request, obj, form, change)

  def response_change(self, request, obj):
      # Check if we need to redirect to confirmation
      if hasattr(request, '_network_update_confirmation_needed') and request._network_update_confirmation_needed:
          return redirect(reverse('admin:network_update_with_confirmation', args=[obj.pk]))
      
      return super().response_change(request, obj)

  def update_with_confirmation_view(self, request, object_id):
      network = Network.objects.get(pk=object_id)
      update_data = request.session.get('network_update_data', {})
      
      if not update_data or update_data.get('object_id') != str(object_id):
          messages.error(request, 'Invalid update session data.')
          return redirect(reverse('admin:networks_network_change', args=[object_id]))

      if request.method == 'POST':
          if 'confirm_update' in request.POST:
              # User confirmed - apply the update and update associated objects
              try:
                  # Get the old values
                  old_subnet = update_data['old_subnet']
                  old_netmask = update_data['old_netmask']
                  
                  # Apply the stored edit through the admin form, so every
                  # field on the form is saved, not just the subnet.
                  form_data = QueryDict(mutable=True)
                  for field, values in update_data['form_data'].items():
                      form_data.setlist(field, values)
                  form = self.get_form(request, network, change=True)(form_data, instance=network)
                  if not form.is_valid():
                      raise ValueError(form.errors.as_text())
                  network = form.save()
                  
                  # Update associated IPs
                  from .utils import update_associated_ips
                  results = update_associated_ips(network, old_subnet, old_netmask)
                  
                  # Clear session data
                  if 'network_update_data' in request.session:
                      del request.session['network_update_data']
                  
                  # Show success message
                  success_msg = 'Network updated successfully. '
                  if results['interfaces_updated'] > 0:
                      success_msg += f'Updated {results["interfaces_updated"]} network interfaces. '
                  if results['bmcs_updated'] > 0:
                      success_msg += f'Updated {results["bmcs_updated"]} BMCs. '
                  messages.success(request, success_msg)
                  if results['errors']:
                      messages.warning(request, f'Errors updating IPs: {"; ".join(results["errors"])}')
                  return redirect(reverse('admin:networks_network_changelist'))
                  
              except Exception as e:
                  messages.error(request, f'Error updating network: {str(e)}')
                  return redirect(reverse('admin:networks_network_change', args=[object_id]))
          
          elif 'cancel_update' in request.POST:
              # User cancelled - clear session data and return to edit form
              if 'network_update_data' in request.session:
                  del request.session['network_update_data']
              messages.info(request, 'Network update cancelled.')
              return redirect(reverse('admin:networks_network_change', args=[object_id]))

      # GET request - show confirmation page
      old_subnet = update_data['old_subnet']
      old_netmask = update_data['old_netmask']
      new_subnet = update_data['new_subnet']
      new_netmask = update_data['new_netmask']
      
      # Get associated objects and calculate proposed changes
      associated = get_associated_objects(network)
      
      # Create temporary network objects for IP calculation
      from .models import Network as NetworkModel
      temp_network = NetworkModel(subnet=new_subnet, netmask=int(new_netmask))
      old_network = NetworkModel(subnet=old_subnet, netmask=int(old_netmask))
      new_ips = calculate_new_ips([i.ipaddress for i in associated['interfaces']] + [b.ipaddress for b in associated['bmcs']], old_network, temp_network)
      
      proposed_interfaces = []
      for interface in associated['interfaces']:
          if interface.ipaddress:
              proposed_ip = new_ips.get(interface.ipaddress)
              if proposed_ip:
                  proposed_interfaces.append({
                      'id': interface.id,
                      'name': interface.name,
                      'system': interface.system.hostname,
                      'current_ip': interface.ipaddress,
                      'proposed_ip': proposed_ip
                  })
      
      proposed_bmcs = []
      for bmc in associated['bmcs']:
          if bmc.ipaddress:
              proposed_ip = new_ips.get(bmc.ipaddress)
              if proposed_ip:
                  proposed_bmcs.append({
                      'id': bmc.id,
                      'system': bmc.system.hostname,
                      'current_ip': bmc.ipaddress,
                      'proposed_ip': proposed_ip
                  })
      
      context = {
          **self.admin_site.each_context(request),
          'title': 'Confirm Network Update',
          'network': network,
          'old_subnet': f"{old_subnet}/{old_netmask}",
          'new_subnet': f"{new_subnet}/{new_netmask}",
          'proposed_interfaces': proposed_interfaces,
          'proposed_bmcs': proposed_bmcs,
          'has_changes': len(proposed_interfaces) > 0 or len(proposed_bmcs) > 0,
          'opts': self.model._meta,
          'is_popup': False,
          'save_as': False,
          'has_change_permission': True,
          'has_view_permission': True,
          'has_add_permission': True,
          'has_delete_permission': True,
      }
      
      return render(request, 'admin/networks/confirm_update.html', context)

class NetworkTypeAdmin(admin.ModelAdmin):
  model = NetworkType
  list_display = ['id', 'name']
  list_display_links = ['id', 'name']

class SwitchPortInline(admin.TabularInline):
  model = SwitchPort
  extra = 1
  list_display = ['name']
  list_display_links = ['id', 'name']
  ordering = ('name',)
    

class SwitchAdmin(admin.ModelAdmin):
  model = Switch
  inlines = [SwitchPortInline]
  readonly_fields = ['created_by']
  list_display = ['id', 'hostname', 'mgmt_ip', 'mgmt_mac', 'network']
  list_display_links = ['id', 'hostname']

admin.site.register(Network, NetworkAdmin)
admin.site.register(NetworkType, NetworkTypeAdmin)
admin.site.register(Switch, SwitchAdmin)
