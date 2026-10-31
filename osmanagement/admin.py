from jobqueue.models import JobModule, queue_job
from django.contrib import admin
from django.db.models import F
from .forms import OSDistro_form
from .models import (
  OSDistro,
  OSRepo,

)
@admin.action(description="Re-sync the selected mirrored repositories.")
def resync_repos(modeladmin, request, queryset):
  try:
      JobType = JobModule.objects.get(slug='repo-update')
  except JobModule.DoesNotExist:
      # do nothing if the jobtype isn't defined.
      return

  # Like RepoUpdateJob, only managed repos are synced by the job servers.
  # An unmanaged repo's version must not change: repo_sync would try to
  # mirror it from /osrepos/<id>/, which no job server hosts.
  for instance in queryset.filter(managed=True):
    # queue a repo-update job.
    queue_job(JobType, { 'repo_id': instance.id})

    # Clear out the hosted_by jobservers and increment the version number.
    # update() saves the version without firing RepoUpdateJob, which would
    # increment it again.
    instance.hosted_by.clear()
    OSRepo.objects.filter(pk=instance.pk).update(version=F('version') + 1)

class OSRepoAdmin(admin.ModelAdmin):
  model=OSRepo
  list_display=['id', 'name', 'repo_package_url', 'managed', 'newest_only', 'version']
  list_display_links=['id','name']
  readonly_fields=['hosted_by']
  actions = [resync_repos]

class OSDistroAdmin(admin.ModelAdmin):
  model = OSDistro
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
