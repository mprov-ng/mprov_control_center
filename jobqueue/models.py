import datetime
import ipaddress
import random
from django.conf import settings
from django.db import models, connections, transaction
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
        # A pending job belongs to no job server: whatever sets one back to
        # pending (a change signal re-queueing it, an admin edit, a PATCH)
        # frees it, so any job server can claim it again (#296).
        if self.status_id == PENDING:
            self.jobserver = None
            # update_or_create() saves only the fields it was given.
            update_fields = kwargs.get('update_fields')
            if update_fields is not None and 'jobserver' not in update_fields:
                kwargs['update_fields'] = list(update_fields) + ['jobserver']
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
RUNNING = 2
ERROR = 3

def filter_params(queryset, params):
    """
    Filter a Job queryset to the jobs whose params have every key of the
    dict params with that value.  On MySQL/MariaDB this uses JSON_CONTAINS
    (params__contains): MariaDB never matches a key lookup against a string
    value, because Django leaves the right-hand side as a quoted JSON string
    there (#385).  SQLite has no JSON_CONTAINS, so other backends use one key
    lookup per key.  Values are meant to be scalars; JSON_CONTAINS would also
    match a nested object or list that only contains the given one.
    """
    if connections[queryset.db].vendor == 'mysql':
        return queryset.filter(params__contains=params)
    for key, value in params.items():
        queryset = queryset.filter(**{f"params__{key}": value})
    return queryset

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

def requeue_job(module, name=None):
    """
    Queue the job named name (the module's name by default) for module again,
    for the change signals that re-run one job per module (#312):
    - a pending one is already queued: leave it;
    - a running one may be using the old data: leave it alone, and queue a
      separate pending job so the change runs after it;
    - otherwise reuse the last finished one as the pending job, so each of
      these stays one row, or create it.
    Returns the pending job.
    """
    name = module.name if name is None else name
    with transaction.atomic():
        jobs = Job.objects.select_for_update().filter(module=module, name=name)
        pending = jobs.filter(status_id=PENDING).first()
        if pending is not None:
            return pending
        if not jobs.filter(status_id=RUNNING).exists():
            finished = jobs.order_by('-pk').first()
            if finished is not None:
                finished.status_id = PENDING
                finished.save()
                return finished
        return Job.objects.create(name=name, module=module, status_id=PENDING)

# a job server, or one of its addresses, with no heartbeat for this long is
# stale: it's left out of routing, not deleted (#254, #435).
STALE_AFTER = datetime.timedelta(seconds=60)

class JobServerQuerySet(models.QuerySet):
    def fresh(self):
        """ The job servers that have heartbeated within STALE_AFTER. """
        return self.filter(heartbeat_time__gt=timezone.now() - STALE_AFTER)

    def stale_for(self, age):
        """ The job servers with no heartbeat for at least age. """
        return self.filter(heartbeat_time__lte=timezone.now() - age)

class JobServer(models.Model):
    """ This area shows you the status of job servers that have registered themselves with the mPCC.  It will show you the IP address that the 
    job server registered with, the port, any job modules it can run, its load average, and when the mPCC last heard from it.

        Usually, you should not have to look at this stuff unless something fails.
    """
    endpoint="/jobservers/"
    name = models.CharField(max_length=255, unique=True)
    # a job server's own stable ID, sent with every heartbeat by job servers
    # that have one, so a rename keeps the same row (mprov_jobserver#113).
    # NULL for job servers that don't send one.
    host_id = models.CharField(max_length=64, unique=True, null=True, blank=True, verbose_name="Host ID")
    address = models.CharField(max_length=1024, default="mprov")
    port = models.IntegerField(verbose_name="Port", default=8080, )
    heartbeat_time = models.DateTimeField(default=timezone.now, verbose_name="Last Heartbeat")
    jobmodules=models.ManyToManyField(JobModule, verbose_name="Handled Job Modules")
    one_minute_load=models.FloatField(verbose_name="1 Minute Load Avg.", default=0.00, null=True)
    network=models.ForeignKey('networks.Network', blank=True, null=True, on_delete=models.SET_NULL)
    objects = JobServerQuerySet.as_manager()
    def __str__(self):
        return self.name
    class Meta:
        verbose_name="Job Server"

    @property
    def responsive(self):
        """ Whether this job server has heartbeated within STALE_AFTER.  An
        unresponsive one is left out of routing, not deleted (#254). """
        return self.heartbeat_time > timezone.now() - STALE_AFTER

    def fail_running_jobs(self):
        """ Fail the jobs this job server is running.  Not re-queued: a
        half-done image build or repo mirror may not be safe to run again
        (#409). """
        for job in Job.objects.filter(jobserver=self, status_id=RUNNING):
            job.status_id = ERROR
            job.end_time = timezone.now()
            job.save()

    def save(self, *args, **kwargs):
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

    def address_for(self, client_ip):
        """
        The address a client at client_ip should use for this job server:
        the one it registered on the client's network, if any
        (mprov_jobserver#114) and it has heartbeated within STALE_AFTER
        (#435), else its single address.  Stale addresses are skipped, not
        deleted.
        """
        try:
            client = ipaddress.ip_address(client_ip)
        except (TypeError, ValueError):
            return self.address
        fresh = self.addresses.filter(heartbeat_time__gt=timezone.now() - STALE_AFTER)
        for entry in fresh.select_related('network').order_by('pk'):
            if entry.network is not None and client in entry.network_range():
                return entry.address
        return self.address


class JobServerAddress(models.Model):
    """ An address a job server serves on one of its networks, from its
    last heartbeat (mprov_jobserver#114). """
    jobserver = models.ForeignKey(JobServer, on_delete=models.CASCADE, related_name='addresses')
    network = models.ForeignKey('networks.Network', blank=True, null=True, on_delete=models.SET_NULL)
    address = models.CharField(max_length=1024)
    heartbeat_time = models.DateTimeField(default=timezone.now, verbose_name="Last Heartbeat")
    # where this address's last heartbeat (POST /jobservers/<pk>/heartbeat/)
    # came from, and the network that's on (#435).  NULL until it has one.
    heard_from = models.CharField(max_length=1024, blank=True, null=True, verbose_name="Heard From")
    heard_from_network = models.ForeignKey('networks.Network', blank=True, null=True, on_delete=models.SET_NULL,
                                           related_name='+', verbose_name="Heard From Network")

    class Meta:
        verbose_name = "Job Server Address"
        constraints = [models.UniqueConstraint(fields=['jobserver', 'address'], name='unique_jobserver_address')]

    def __str__(self):
        return f"{self.jobserver}: {self.address}"

    def network_range(self):
        """ This address's network as an ipaddress network, or an empty one. """
        return network_range(self.network)


def network_range(network):
    """ A Network as an ipaddress network, or an empty one. """
    try:
        return ipaddress.ip_network(f"{network.subnet}/{network.netmask}", strict=False)
    except (AttributeError, ValueError):
        return ()


def route_order(jobservers, client_ip):
    """
    The responsive job servers of a queryset (an image's or a repo's), in
    the order a client at client_ip should try them (#254): those with an
    address on the client's network first, then the rest, each by one
    minute load (unknown last), ties in random order.  An address on the
    client's network is one it registered there (address_for(),
    mprov_jobserver#114) or its single address, if that's in one of the
    networks the client is in.  Each one's route_address is the address
    the client should use.
    """
    from networks.models import Network
    try:
        client = ipaddress.ip_address(client_ip)
        client_networks = [r for r in map(network_range, Network.objects.all()) if client in r]
    except (TypeError, ValueError):
        client_networks = []

    def on_client_network(address):
        try:
            address = ipaddress.ip_address(address)
        except ValueError:
            return False
        return any(address in r for r in client_networks)

    servers = list(jobservers.fresh())
    for server in servers:
        server.route_address = server.address_for(client_ip)
    random.shuffle(servers)
    servers.sort(key=lambda s: (not on_client_network(s.route_address),
                                float('inf') if s.one_minute_load is None else s.one_minute_load))
    return servers


def sweep_stale_jobservers():
    """
    Stale job servers are kept, not deleted (#254).  Fail the RUNNING jobs of
    those stale for JOBSERVER_FAIL_JOBS_AFTER_MINUTES, and delete those stale
    for JOBSERVER_DELETE_AFTER_DAYS (0 turns either off).  Deleting goes
    through the usual signals, which also fail its jobs and queue repo
    updates.  Run from registration heartbeats, at most once a minute.
    """
    if settings.JOBSERVER_FAIL_JOBS_AFTER_MINUTES > 0:
        age = datetime.timedelta(minutes=settings.JOBSERVER_FAIL_JOBS_AFTER_MINUTES)
        for server in JobServer.objects.stale_for(age).filter(job__status_id=RUNNING).distinct():
            print(f"Info: failing the running jobs of unresponsive job server {server}.")
            server.fail_running_jobs()
    if settings.JOBSERVER_DELETE_AFTER_DAYS > 0:
        age = datetime.timedelta(days=settings.JOBSERVER_DELETE_AFTER_DAYS)
        for server in JobServer.objects.stale_for(age):
            print(f"Info: deleting job server {server}, unresponsive for over {settings.JOBSERVER_DELETE_AFTER_DAYS} days.")
            server.delete()


@receiver(pre_save, sender=JobServer)
def convertJobServerTS(sender, instance, **kwargs):
    if not is_aware(instance.heartbeat_time):
        instance.heartbeat_time = make_aware(instance.heartbeat_time)
