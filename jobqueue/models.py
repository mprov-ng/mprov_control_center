import ipaddress, time, datetime
from tabnanny import verbose
from django.db import models
from django.apps import apps
from django.utils.timezone import make_aware
from django.utils import timezone


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
        # add some default dependancies
        if self.module.slug == "image-update":
            self.params.update({"deps": "repo-sync"})
        super(Job, self).save(*args, **kwargs)
        
class JobModule(models.Model):
    """ Job Modules are the types of jobs that a job server can execute.  These usually define what jobserver modules/plugins will
    be run.  They also serve as a point to breakup job server tasks to multiple jobservers, if you desire.

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

class JobServer(models.Model):
    """ This area shows you stauts on job servers that have registered themselves with the mPCC.  It will show you the IP address that the 
    job server registered with, the port, any job modules it can run, it's load average, and when the mPCC last heard from it.

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

    # XXX: With the correct related fields on the serializer, do we need this?
    def save(self, *args, **kwargs):
        # check for stale servers
        # only run if we are on a 5 minute boundry
        # print(f"{int(time.time()) % 10}")
        if int(time.time() % 60) == 0:
            # delete any servers that are older than 1 minute heartbeat.
            delTime = time.time() - 60
            delDateTime = datetime.datetime.fromtimestamp(delTime)#.strftime("%Y-%m-%d %H:%M:%S")
            delDateTime = make_aware(delDateTime)
            print("Info: Removing stale jobservers.")
            self.__class__.objects.filter(heartbeat_time__lte=delDateTime).delete()
        
        # search for a network that our address is in.
        myaddr = ipaddress.ip_address(self.address)
        # get a ref to the networks class
        networkcls = apps.get_model('networks.Network')
        networks = networkcls.objects.all()
        found_net = None
        for network in networks:
            ipnet = network.subnet
            ipmask = network.netmask
            mynet = ipaddress.ip_network(f"{ipnet}/{ipmask}")
            if myaddr in mynet:
                found_net = network
                break
        if found_net != None:
            self.network = found_net
        super().save(*args, **kwargs)