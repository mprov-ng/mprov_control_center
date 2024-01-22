from statistics import mode
from django.contrib import admin
from .forms import OSDistro_form
from .models import (
  OSDistro,
  OSRepo,

)
class OSRepoAdmin(admin.ModelAdmin):
  model=OSRepo
  list_display=['id', 'name', 'repo_package_url', 'managed', 'version']
  list_display_links=['id','name']
  readonly_fields=['hosted_by']

class OSDistroAdmin(admin.ModelAdmin):
  model = OSDistro,
  form = OSDistro_form
  #inlines = [RepoInline]
  list_display=['id', 'name', 'vendor', 'version']
  list_display_links=['id', 'name']
  readonly_fields = ['osrepos']
  fieldsets = (
    (None, {
      'fields': (
        'name',
        'vendor',
        'version',
        'distType',
        'distArch',
        'managed',
        'update',
        'baseurl',
        'baserepo',
        'osrepos',
        'extrarepos',


      )
    }),
    ('OS Configuration', {
      'fields':(
        'rootpw',
        'rootsshkeys',
        'config_params',
        'scripts',
        'ansiblecollections',
        'ansibleplaybooks',
        'ansibleroles',
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
