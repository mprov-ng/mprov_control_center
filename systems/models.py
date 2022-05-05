from operator import mod
from django.db import models
from django.conf import settings
from django.dispatch import receiver
from django.forms import CharField, PasswordInput, ModelForm
from networks.models import SwitchPort
from osmanagement.models import OSDistro, OSRepo
from django.db.models.signals import pre_save, pre_delete, post_save
from jobqueue.models import JobModule, JobStatus, Job, JobServer
from django.utils.text import slugify
from scripts.models import Script

class SystemGroup(models.Model):
  name=models.CharField(max_length=255)
  scripts = models.ManyToManyField(Script, blank=True, )
  config_params=models.TextField(
    blank=True, 
    default="-- # Inherit from OS", 
    verbose_name="Configuration Parameters"
  )

  class Meta:
    ordering = ['name']
    verbose_name = "System Group"
    verbose_name_plural = "System Groups"
  
  def __str__(self):
    return self.name


class System(models.Model):
  hostname=models.CharField(max_length=255, verbose_name="Host Name")
  timestamp=models.DateTimeField(auto_now_add=True, verbose_name="Created")
  created_by=models.ForeignKey(
    settings.AUTH_USER_MODEL, 
    on_delete=models.SET(1),
    verbose_name="Created By"
  )
  updated=models.DateTimeField(auto_now=True, verbose_name="Lasted Updated")
  systemgroups = models.ManyToManyField(SystemGroup, verbose_name="System Groups",blank=True)
  scripts = models.ManyToManyField(Script, blank=True, )
  config_params = models.TextField(
    default="-- #Inherit from System Group or Distrubtion.",
    verbose_name="Configuration\nParameters",
    blank=True,
    null=True,
  )
  systemimage = models.ForeignKey('SystemImage', blank=True, null=True, on_delete=models.SET_NULL)
 
  class Meta:
    ordering = ['hostname']
    verbose_name = 'Systems'
    verbose_name_plural = 'Systems'
  
  def __str__(self):
    return self.hostname


class SystemBMC(models.Model):
  
  system = models.ForeignKey(System, on_delete=models.CASCADE)
  ipaddress=models.GenericIPAddressField(verbose_name="IP Address ")
  mac=models.CharField(max_length=100, verbose_name="MAC Address", blank=True, null=True)
  username=models.CharField(max_length=255, verbose_name="BMC User", blank=True, null=True)
  password=models.CharField(max_length=100, verbose_name="BMC Password", blank=True, null=True)
  switch_port=models.ForeignKey(SwitchPort, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Switch Port")
  class Meta:
    verbose_name = 'Power Management'
    verbose_name_plural = 'Power Management'

  
  def __str__(self):
    return self.system.name + " BMC"

class SystemBMCForm(ModelForm):
  password = CharField(widget=PasswordInput())
  class Meta:
      model = SystemBMC
      fields = '__all__'

class NetworkInterface(models.Model):
  system = models.ForeignKey(System, on_delete=models.CASCADE)
  name=models.CharField(max_length=120, verbose_name="Interface Name(eg. eth0)")
  hostname=models.CharField(max_length=255, )
  ipaddress=models.GenericIPAddressField(verbose_name="IP Address ")
  mac=models.CharField(max_length=100, verbose_name="MAC Address", blank=True, null=True)
  switch_port=models.ForeignKey(SwitchPort, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Switch Port")


class SystemImage(models.Model):
  name=models.CharField(max_length=255, verbose_name="Image Name",unique=True,)
  slug=models.SlugField(max_length=255, unique=True, editable=False, verbose_name='Image ID', primary_key=True)
  timestamp=models.DateTimeField(auto_now_add=True, verbose_name="Created")
  created_by=models.ForeignKey(
    settings.AUTH_USER_MODEL, 
    on_delete=models.SET(1),
    verbose_name="Created By",
  )
  updated=models.DateTimeField(auto_now=True, verbose_name="Lasted Updated")
  systemgroups = models.ManyToManyField(SystemGroup, verbose_name="System Groups",blank=True)
  scripts = models.ManyToManyField(Script, blank=True, )

  needs_rebuild = models.BooleanField(default=True, verbose_name="Rebuild Image?")
  version = models.BigIntegerField(default=1, verbose_name="Image Version")
  jobservers = models.ManyToManyField(JobServer, verbose_name="Hosted By", blank=True)
  config_params = models.TextField(
    default="-- #Inherit from System Group or Distrubtion.",
    verbose_name="Configuration\nParameters",
    blank=True,
    null=True,
  )
  osdistro = models.ForeignKey(
    OSDistro,
    blank=True, 
    null=True, 
    on_delete=models.SET_NULL,
    verbose_name="OS Distrubution",
    related_name="distro"
  )
  osrepos=models.ManyToManyField(
    OSRepo, 
    blank=True,
    verbose_name="OS Repositories"
  )
  class Meta:
    ordering = ['name']
    verbose_name = 'System Image'

  def __str__(self):
    return self.name

# emits jobs to update dns, dhcp, and pxe config if a 
# system, systemimage, or NIC is changed.
# TODO: add the sender information to the
# job params? Or should we just rebuild it all.
@receiver(pre_save, sender=SystemImage)
@receiver(pre_save, sender=System)
@receiver(pre_save, sender=NetworkInterface)
def UpdateSystemAttributes(sender, instance, **kwargs):
  
  if sender == SystemImage or sender == System:
    import inspect
    for frame_record in inspect.stack():
        if frame_record[3]=='get_response':
            request = frame_record[0].f_locals['request']
            break
    else:
        request = None
    if request is not None:
      instance.created_by = request.user
  for slug in ['pxe-update', 'dns-update', 'dhcp-update']:
    JobType = None
    try:
        JobType = JobModule.objects.get(slug=slug)
    except:
        JobType = None
    print(JobType)
    # get or create the OSIMAGE_UPDATE job module in the DB
    # get the jobtype, do nothing if it's not defined.
    if JobType is not None:
        # save a new job, if one doesn't already exist.

        Job.objects.update_or_create(
          name=JobType.name , module=JobType,
          defaults={'status': JobStatus.objects.get(pk=1)}
        )

# emit image-delete jobs for every server that currently 
# hosts a deleted image.
@receiver(pre_delete, sender=SystemImage)
def DeleteSystemImage(sender, instance, **kwargs):
  # grab a copy of the jobservers.
  jobservers = list(instance.jobservers.all())
  print(jobservers)
  # now clear this so everyone stops serving it.
  instance.jobservers.clear()


  JobType = None
  try:
      JobType = JobModule.objects.get(slug='image-delete')
  except:
      JobType = None
  # get the jobtype, do nothing if it's not defined.
  if JobType is not None:
    # submit an image-delete job for every jobserver in
    # the list of jobservers this image is hosted on
    params = { 'imageId': instance.slug}
    for jobserver in jobservers:
      print("Job for " + str(jobserver))
      Job.objects.create( name=JobType.name, 
        module=JobType, 
        status=JobStatus.objects.get(pk=1), 
        params = params,
        jobserver = jobserver,
      )
  else:
    print("JobType was none.  HuH?")
  pass

# emits an image-update job everytime an image is modified.
@receiver(pre_save, sender=SystemImage)
def UpdateSystemImages(sender, instance, **kwargs):
  if not instance.needs_rebuild: 
    return
  instance.slug = slugify(instance.name)

  JobType = None
  try:
      JobType = JobModule.objects.get(slug='image-update')
  except:
      JobType = None
  # print(str(JobType) + " post")

  # get the jobtype, do nothing if it's not defined.
  if JobType is not None:

      # save a new job, if one doesn't already exist.
      params = { 'imageId': instance.slug}
      Job.objects.create( name=JobType.name, 
          module=JobType, 
          status=JobStatus.objects.get(pk=1), 
          params = params,
      )

      # TODO: Increment version number and clear out jobservers field.
      instance.jobservers.clear()
      instance.version = instance.version + 1