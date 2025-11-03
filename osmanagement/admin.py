from jobqueue.models import JobModule, JobStatus, Job
from django.contrib import admin
from .forms import OSDistro_form
from .models import (
  OSDistro,
  OSRepo,

)
@admin.action(description="Mark repositories as needing update.")
def mark_update(modeladmin, request, queryset):
  queryset.update(update=True)
  for instance in queryset:
    if not instance.update: 
      return

    JobType = None
    try:
        JobType = JobModule.objects.get(slug='repo-update')
    except:
        JobType = None
    # print(str(JobType) + " post")

    # get the jobtype, do nothing if it's not defined.
    if JobType is not None:

        # save a new job, if one doesn't already exist.
        params = { 'repo_id': instance.id}
        Job.objects.create( name=JobType.name, 
            module=JobType, 
            status=JobStatus.objects.get(pk=1), 
            params = params,
        )

        # Increment version number and clear out jobservers field.
        instance.hosted_by.clear()
        instance.version = instance.version + 1

class OSRepoAdmin(admin.ModelAdmin):
  model=OSRepo
  list_display=['id', 'name', 'repo_package_url', 'managed', 'version']
  list_display_links=['id','name']
  readonly_fields=['hosted_by']
  actions = [mark_update]

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
