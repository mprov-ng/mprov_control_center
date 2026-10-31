from django.contrib import admin
from .models import Job, JobModule, JobServer, JobServerAddress

class JobAdmin(admin.ModelAdmin):
    model = Job
    readonly_fields = ('return_code', 'params', 'module','jobserver',)#'status', ) 
    list_display = ['name', 'status','create_time', 'start_time', 'end_time', 'last_update','jobserver']
    
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['job_status_changes_url'] = '/jobqueue/status-changes/'
        return super().changelist_view(request, extra_context=extra_context)
    
    class Media:
        js = (
            "admin/js/auto_reload.js",
        )
    def has_add_permission(self, request):
        return ("add" in request.path or "change" in request.path)
class JobModuleAdmin(admin.ModelAdmin):
    model = JobModule
    readonly_fields = ('active',  )
    list_display=['name', 'slug']
    list_display_links=['name']    
    exclude = ('slug', )

    def has_add_permission(self, request):
        return ("add" in request.path or "change" in request.path)

class JobServerAddressInline(admin.TabularInline):
    """ The addresses from the job server's last heartbeat (mprov_jobserver#114). """
    model = JobServerAddress
    fields = ('address', 'network', 'heartbeat_time', 'heard_from', 'heard_from_network')
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class JobServerAdmin(admin.ModelAdmin):
    model = JobServer
    inlines = [JobServerAddressInline]
    readonly_fields = ('host_id', 'address','heartbeat_time','jobmodules',)
    list_display = ['name', 'host_id', 'address', 'port', 'registered_jobmodules', 'heartbeat_time', 'one_minute_load'  ]
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related('jobmodules')

    def registered_jobmodules(self, obj):
        return ", ".join([jm.slug for jm in obj.jobmodules.all()])
    registered_jobmodules.short_description = 'Registered Job Modules'

    def has_add_permission(self, request):
        return ("add" in request.path or "change" in request.path)

admin.site.register(Job, JobAdmin)
admin.site.register(JobModule, JobModuleAdmin)
admin.site.register(JobServer, JobServerAdmin)
