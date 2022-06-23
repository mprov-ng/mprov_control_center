from statistics import mode
from django.contrib import admin

from .models import (
  OSDistro,
  OSRepo,

)
class OSRepoAdmin(admin.ModelAdmin):
  model=OSRepo
  list_display=['id', 'name', 'repo_package_url']
  list_display_links=['id','name']

# class RepoInline(admin.StackedInline):
#   model = OSRepo
#   extra=0
#   list_display=['id', 'name']
#   list_display_links=['id', 'name']

class OSDistroAdmin(admin.ModelAdmin):
  model = OSDistro,
  #inlines = [RepoInline]
  list_display=['id', 'name', 'vendor', 'version']
  list_display_links=['id', 'name']
  fieldsets = (
    (None, {
      'fields': (
        'name',
        'vendor',
        'baserepo',
        'osrepos',

      )
    }),
    ('OS Configuration', {
      'fields':(
        'config_params',
        'scripts',
        'install_kernel_cmdline',
        'tmpfs_root_size',
        'initial_mods',
        'prov_interface',
      )
    }
    ),
  )


admin.site.register(OSDistro, OSDistroAdmin)
admin.site.register(OSRepo, OSRepoAdmin)