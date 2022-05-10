from tabnanny import verbose
from django.db import models

class Job(models.Model):
    name=models.CharField(max_length=255)
    create_time=models.DateTimeField(auto_now_add=True, verbose_name="Created Time")
    start_time=models.DateTimeField(blank=True, null=True, verbose_name="Start Time")
    end_time = models.DateTimeField(blank=True, null=True, verbose_name="End Time")
    last_update = models.DateTimeField(auto_now=True, blank=True, null=True, verbose_name="Last Update")
    return_code = models.IntegerField(blank=True, null=True, verbose_name='Return Code')
    module = models.ForeignKey('JobModule', on_delete=models.CASCADE)
    params = models.JSONField(verbose_name="Job Parameters", default=dict, null=True)
    status = models.ForeignKey('JobStatus', on_delete=models.CASCADE, default=1)
    jobserver = models.ForeignKey('JobServer', on_delete=models.SET_NULL, null=True, verbose_name="Assigned Job Server")
    def __str__(self):
        return self.name
    class Meta:
        verbose_name="Job"
        verbose_name_plural="Jobs"

class JobModule(models.Model):
    name = models.CharField(max_length=255)
    active = models.IntegerField(default=0)
    slug = models.SlugField(max_length=255, unique=True, editable=False, verbose_name='Module ID', primary_key=True)

    def __str__(self):
        return self.name
    class Meta:
        verbose_name="Job Module"
class JobStatus(models.Model):
    name = models.CharField(max_length=100)
    def __str__(self):
        return self.name
    class Meta:
        verbose_name="Job Status"

class JobServer(models.Model):
    name = models.CharField(max_length=255, unique=True)
    address = models.GenericIPAddressField()
    port = models.IntegerField(verbose_name="Port", default=80, )
    heartbeat_time = models.DateTimeField(auto_now=True, verbose_name="Last Heart Beat")
    jobmodules=models.ManyToManyField(JobModule, verbose_name="Handled Job Modules")
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name="Job Server"