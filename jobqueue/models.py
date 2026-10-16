import datetime
from django.db import models
from django.utils.timezone import make_aware, is_aware
from django.utils import timezone
from django.dispatch import receiver
from django.db.models.signals import pre_save

class Job(models.Model):
    """Jobs are internal mProv jobs that are run by the Jobservers. Jobs function to do tasks on behalf of the mPCC.  

    Usually, you should not have to look at this stuff unless something fails.
    """
    endpoint="/jobs/"
    name=models.CharField(max_length=255)
    create_time=models.DateTimeField(default=timezone.now, verbose_name="Created Time")
    start_time=models.DateTimeField(blank=True, null=True, verbose_name="Start Time")
    end_time = models.DateTimeField(blank=True, null=True, verbose_name="End Time")
    last_update = models.DateTimeField(default=timezone.now, blank=True, null=True, verbose_name="Last Update")
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
    def save(self, *args, **kwargs):
        # add some default dependencies
        if self.module.slug == "image-update":
            self.params.update({"deps": "repo-sync"})
        super(Job, self).save(*args, **kwargs)
        
class JobModule(models.Model):
    """ Job Modules are the types of jobs that a job server can execute.  These usually define what jobserver modules/plugins will
    be run.  They also serve as a point to break up job server tasks to multiple jobservers, if you desire.

        Usually, you should not have to look at this stuff unless something fails.
    """
    endpoint="/jobmodules/"
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

PENDING = 1

def queue_job(module, params=None):
    """
    Queue a pending job for module with params, unless an identical job is
    already pending, so repeated triggers don't pile up duplicate jobs.
    Returns the new or existing job.
    """
    params = {} if params is None else params
    job = Job.objects.filter(module=module, status_id=PENDING, params=params).first()
    if job is None:
        job = Job.objects.create(name=module.name, module=module, status=JobStatus.objects.get(pk=PENDING), params=params)
    return job

class JobServer(models.Model):
    """ This area shows you the status of job servers that have registered themselves with the mPCC.  It will show you the IP address that the 
    job server registered with, the port, any job modules it can run, its load average, and when the mPCC last heard from it.

        Usually, you should not have to look at this stuff unless something fails.
    """
    endpoint="/jobservers/"
    name = models.CharField(max_length=255, unique=True)
    address = models.CharField(max_length=1024, default="mprov")
    port = models.IntegerField(verbose_name="Port", default=8080, )
    heartbeat_time = models.DateTimeField(default=timezone.now, verbose_name="Last Heart Beat")
    jobmodules=models.ManyToManyField(JobModule, verbose_name="Handled Job Modules")
    one_minute_load=models.FloatField(verbose_name="1 Minute Load Avg.", default=0.00, null=True)
    network=models.ForeignKey('networks.Network', blank=True, null=True, on_delete=models.SET_NULL)
    def __str__(self):
        return self.name
    class Meta:
        verbose_name="Job Server"

    def save(self, *args, **kwargs):
        # delete any other servers whose last heartbeat is more than a
        # minute old.  Job servers save on every heartbeat (every 10
        # seconds by default), so this runs often.
        delDateTime = timezone.now() - datetime.timedelta(seconds=60)
        stale = self.__class__.objects.filter(heartbeat_time__lte=delDateTime).exclude(pk=self.pk)
        if stale.exists():
            print("Info: Removing stale jobservers.")
            stale.delete()
        
        # search for a network that our address is in.
        #myaddr = ipaddress.ip_address(self.address)
        # get a ref to the networks class
        #networkcls = apps.get_model('networks.Network')
        #networks = networkcls.objects.all()
        #found_net = None
        #for network in networks:
        #    ipnet = network.subnet
        #    ipmask = network.netmask
        #    mynet = ipaddress.ip_network(f"{ipnet}/{ipmask}")
        #    if myaddr in mynet:
        #        found_net = network
        #        break
        #if found_net != None:
        #    self.network = found_net
        super().save(*args, **kwargs)


@receiver(pre_save, sender=JobServer)
def convertJobServerTS(sender, instance, **kwarg):
    if not is_aware(instance.heartbeat_time):
        instance.heartbeat_time = make_aware(instance.heartbeat_time)
