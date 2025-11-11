from django.contrib import admin, messages
from django.shortcuts import render, redirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.http import HttpResponseRedirect
from .models import Network, NetworkType, Switch, SwitchPort
from .utils import get_associated_objects, calculate_new_ip


class NetworkAdmin(admin.ModelAdmin):
  model = Network
  # Removing vlan for now.
  #list_display = ['slug', 'name', 'net_type', 'vlan', 'subnet', 'netmask']
  list_display = ['slug', 'name', 'net_type', 'subnet', 'netmask']
  readonly_fields = ['slug']
  list_display_links = ['slug', 'name',]
  exclude = ('slug',)

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
                  
                  # Update the network with new values
                  network.subnet = update_data['new_subnet']
                  network.netmask = int(update_data['new_netmask'])
                  
                  # Update other fields from form data
                  form_data = update_data['form_data']
                  network.name = form_data.get('name', [network.name])[0] if form_data.get('name') else network.name
                  network.gateway = form_data.get('gateway', [None])[0] if form_data.get('gateway') else None
                  network.nameserver1 = form_data.get('nameserver1', [None])[0] if form_data.get('nameserver1') else None
                  network.domain = form_data.get('domain', [''])[0] if form_data.get('domain') else ''
                  network.isdhcp = 'isdhcp' in form_data
                  network.managedns = 'managedns' in form_data
                  network.isbootable = 'isbootable' in form_data
                  network.dhcpstart = form_data.get('dhcpstart', [None])[0] if form_data.get('dhcpstart') else None
                  network.dhcpend = form_data.get('dhcpend', [None])[0] if form_data.get('dhcpend') else None
                  
                  network.save()
                  
                  # Update associated IPs
                  from .utils import update_associated_ips
                  results = update_associated_ips(network, old_subnet, old_netmask)
                  
                  # Clear session data
                  if 'network_update_data' in request.session:
                      del request.session['network_update_data']
                  
                  # Show success message
                  success_msg = f'Network updated successfully. '
                  if results['interfaces_updated'] > 0:
                      success_msg += f'Updated {results["interfaces_updated"]} network interfaces. '
                  if results['bmcs_updated'] > 0:
                      success_msg += f'Updated {results["bmcs_updated"]} BMCs. '
                  if results['errors']:
                      success_msg += f'Errors: {"; ".join(results["errors"])}'
                  
                  messages.success(request, success_msg)
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
      
      proposed_interfaces = []
      for interface in associated['interfaces']:
          if interface.ipaddress:
              print(f"DEBUG: Calculating IP for {interface.system.hostname}.{interface.name}")
              print(f"  Current IP: {interface.ipaddress}")
              print(f"  Old network: {old_network.subnet}/{old_network.netmask}")
              print(f"  New network: {temp_network.subnet}/{temp_network.netmask}")
              proposed_ip = calculate_new_ip(interface.ipaddress, old_network, temp_network)
              print(f"  Proposed IP: {proposed_ip}")
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
              proposed_ip = calculate_new_ip(bmc.ipaddress, old_network, temp_network)
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
