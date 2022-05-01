from django.contrib import admin
from .models import Network, NetworkType, Switch, SwitchPort

class NetworkAdmin(admin.ModelAdmin):
  model = Network
  list_display = ['slug', 'name', 'net_type', 'vlan', 'subnet', 'netmask']
  readonly_fields = ['slug']
  list_display_links = ['slug', 'name',]


class NetworkTypeAdmin(admin.ModelAdmin):
  model = NetworkType
  list_display = ['id', 'name']
  list_display_links = ['id', 'name']

class SwitchPortInline(admin.StackedInline):
  model = SwitchPort
  extra = 1
  list_display = ['name']
  list_display_links = ['id', 'name']
    

class SwitchAdmin(admin.ModelAdmin):
  model = Switch
  inlines = [SwitchPortInline]
  list_display = ['id', 'hostname', 'mgmt_ip', 'mgmt_mac', 'network']
  list_display_links = ['id', 'hostname']

admin.site.register(Network, NetworkAdmin)
admin.site.register(NetworkType, NetworkTypeAdmin)
admin.site.register(Switch, SwitchAdmin)