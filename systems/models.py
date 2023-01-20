from operator import mod
from django.db import models
from django.conf import settings
from django.dispatch import receiver
from django.forms import CharField, PasswordInput, ModelForm
from disklayouts.models import DiskLayout
from networks.models import SwitchPort, Network
from osmanagement.models import OSDistro, OSRepo
from django.db.models.signals import pre_save, pre_delete, post_save
from jobqueue.models import JobModule, JobStatus, Job, JobServer
from django.utils.text import slugify
from scripts.models import Script
from disklayouts.models import *
from django.contrib.auth.models import AnonymousUser, User
import yaml

class SystemGroup(models.Model):
  name=models.CharField(max_length=255)
  scripts = models.ManyToManyField(Script, blank=True, )
  install_kernel_cmdline=models.CharField(max_length=4096, default="",help_text="Options to pass to the install kernel", blank=True)
  # install kernel parameters.
  tmpfs_root_size = models.IntegerField(default=0, help_text="Size of the root tmpfs filesystem in Gibabytes, 0 inherits from parent Group/Distro")
  initial_mods = models.CharField(default="", help_text="Comma separated list of modules to load.", max_length=255, blank=True)
  prov_interface = models.CharField(default="", help_text="Interface name to provision over.", max_length=255, blank=True)

  endpoint="/systemgroups/"
  config_params=models.TextField(
    blank=True, 
    default="# Inherit from OS", 
    verbose_name="Configuration Parameters"
  )

  class Meta:
    ordering = ['name']
    verbose_name = "System Group"
    verbose_name_plural = "System Groups"
  
  def __str__(self):
    return self.name

class SystemModel(models.Model):
  slug = models.SlugField(primary_key=True, blank=True )
  name = models.CharField(verbose_name="Model Name", max_length=255)
  vendor = models.CharField(verbose_name="Vendor Name", max_length=255)

  class Meta:
    verbose_name = "System Models"
    verbose_name_plural = "System Models"

  def __str__(self) -> str:
     return f"{self.vendor}/{self.name}"

  def save(self, *args, **kwargs):
    if not self.slug:
      self.slug = slugify(f"{self.vendor} {self.name}")
    super(SystemModel, self).save(*args, **kwargs)


class System(models.Model):
  endpoint="/systems/"
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
    default="# Inherit from System Group or Distribtion.",
    verbose_name="Configuration\nParameters",
    blank=True,
    null=True,
  )
  install_kernel_cmdline=models.CharField(max_length=4096, default="",help_text="Options to pass to the install kernel", blank=True)
  # install kernel parameters.
  tmpfs_root_size = models.IntegerField(default=0, help_text="Size of the root tmpfs filesystem in Gibabytes, 0 inherits from parent Group/Distro")
  initial_mods = models.CharField(default="", help_text="Comma separated list of modules to load.", max_length=255, blank=True)
  prov_interface = models.CharField(default="", help_text="Interface name to provision over.", max_length=255, blank=True)

  systemimage = models.ForeignKey('SystemImage', blank=True, null=True, on_delete=models.SET_NULL, verbose_name="System Image")
  systemmodel = models.ForeignKey('SystemModel', blank=True, null=True, on_delete=models.SET_NULL, verbose_name="System Model")
  disks = models.ManyToManyField('disklayouts.Disklayout', blank=True, through=DiskLayout.systems.through)
  # bootdisk = models.ForeignKey(DiskLayout, blank=True, null=True, on_delete=models.SET_NULL, verbose_name="Boot Disk Layout", help_text="Boot disk layout for stateful installs")
  stateful = models.BooleanField(default=False, verbose_name="Stateful System?", help_text="Should this system use images to disk?")
  config = {}
  class Meta:
    ordering = ['hostname']
    verbose_name = 'Systems'
    verbose_name_plural = 'Systems'
  
  inheritableFields=['install_kernel_cmdline', 'tmpfs_root_size', 'initial_mods', 'prov_interface', 'config_params']

  def __str__(self):
    return self.hostname

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.flatten_config()

  
  def flatten_config(self):
    if self.id is None:
      return
    # Used to merge the OS Distro level params, and any System Group
    # params to the system's stuff.

    # loop through our fields and see if OS Distro has anything, assign it to
    # the config dict.
    if hasattr(self, "systemimage"):
      if hasattr(self.systemimage, "osdistro"):
        try:
          for field in self.systemimage.osdistro._meta.get_fields():
            field = field.name
            if field in self.inheritableFields:
              self.config[field] = getattr(self.systemimage.osdistro, field)
        except Exception as e:
          print(f"Error processing OS Distro config. {e}")
        
      
    # Then loop through our system groups, and check each for this field
    # adding it to the config dict
    if hasattr(self, "systemgroups"):
      if self.systemgroups.count() > 0:
        for systemgroup in self.systemgroups.all():
          for field in systemgroup._meta.get_fields():
            field = field.name
            if field in self.inheritableFields:
              # system groups are higher inheritance than OS distro.
              sysgrpfield = getattr(systemgroup, field)
              if type(sysgrpfield) == str:
                if sysgrpfield != "" :
                  lines = sysgrpfield.split("\n")
                  for line in lines:
                    if line.startswith("#"):
                      lines.remove(line)
                  filteredfield = "\n".join(lines)
                  if filteredfield != "":
                    if field == 'install_kernel_cmdline' or field == 'initial_mods':
                      if sysgrpfield[0] == "=":
                        # user is asking us to overwrite the field here.
                        self.config[field] = sysgrpfield[1:]
                      else:
                        # no specifier, let's append
                        if field == 'install_kernel_cmdline':
                          # kernel cmdline is space separated.
                          self.config[field] += f" {sysgrpfield}"
                        else:
                          # mod list is comma separated.
                          self.config[field] += f",{sysgrpfield}"
                    else: 
                      # everything else overwrites.
                      self.config[field] = sysgrpfield
              elif type(sysgrpfield) == int:
                if sysgrpfield != 0:
                  self.config[field] = sysgrpfield
          
    # finally see if the object has it set on it's top-level and overwrite it to the 
    # config dict.
    for field in self._meta.get_fields():
      field = field.name
      if field in self.inheritableFields:
        # system attr are highest inheritance
        sysfield = getattr(self, field)
        if type(sysfield) == str:
          if sysfield != "" :
            lines = sysfield.split("\n")
            for line in lines:
              if line.startswith("#"):
                lines.remove(line)
            filteredfield = "\n".join(lines)
            if filteredfield != "":
              if field == 'install_kernel_cmdline' or field == 'initial_mods':
                if sysfield[0] == "=":
                  # user is asking us to overwrite the field here.
                  self.config[field] = sysfield[1:]
                else:
                  # no specifier, let's append
                  if field == 'install_kernel_cmdline':
                    # kernel cmdline is space separated.
                    self.config[field] += f" {sysfield}"
                  else:
                    # mod list is comma separated.
                    self.config[field] += f",{sysfield}"
              else: 
                # everything else overwrites.
                self.config[field] = sysfield
        elif type(sysfield) == int:
          if sysfield != 0:
            
            self.config[field] = sysfield

class SystemBMC(models.Model):
  endpoint="/systembmcs/"
  system = models.ForeignKey(System, on_delete=models.CASCADE)
  ipaddress=models.GenericIPAddressField(verbose_name="IP Address ")
  mac=models.CharField(max_length=100, verbose_name="MAC Address", blank=True, null=True)
  username=models.CharField(max_length=255, verbose_name="BMC User", blank=True, null=True)
  password=models.CharField(max_length=100, verbose_name="BMC Password", blank=True, null=True)
  switch_port=models.ForeignKey(SwitchPort, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Switch Port")
  network=models.ForeignKey(Network, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Network")
  ipv6ll=models.GenericIPAddressField(verbose_name="IPv6 LL Address ", blank=True, null=True)
  class Meta:
    verbose_name = 'Power Management'
    verbose_name_plural = 'Power Management'

  
  def __str__(self):
    return self.system.hostname + "-bmc"

class SystemBMCForm(ModelForm):
  password = CharField(widget=PasswordInput(),required=False)

  class Meta:
      model = SystemBMC
      fields = '__all__'

  def clean(self):
    password = self.cleaned_data['password']
    if not password or password == "":
      del self.cleaned_data['password']
    print(self.cleaned_data)
    return self.cleaned_data

class NetworkInterface(models.Model):
  endpoint="/networkinterfaces/"
  system = models.ForeignKey(System, on_delete=models.CASCADE)
  name=models.CharField(max_length=50, verbose_name="Iface. Name",)
  hostname=models.CharField(max_length=255, )
  ipaddress=models.GenericIPAddressField(verbose_name="IP Address ", blank=True, null=True)
  ipv6ll=models.GenericIPAddressField(verbose_name="IPv6 LL Address", blank=True, null=True)
  mac=models.CharField(max_length=100, verbose_name="MAC Address", blank=True, null=True)
  switch_port=models.OneToOneField(SwitchPort, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Switch Port")
  bootable=models.BooleanField(default=False,null=True, blank=True)
  ipv6gua=models.GenericIPAddressField(verbose_name="IPv6 SLAAC GUA", blank=True, null=True)

  def __str__(self):
    return self.name

class SystemImage(models.Model):
  endpoint="/systemimages/"
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
    default="# Inherit from System Group or Distribtion.",
    verbose_name="Configuration\nParameters",
    blank=True,
    null=True,
  )
  osdistro = models.ForeignKey(
    OSDistro,
    blank=True, 
    null=True, 
    on_delete=models.SET_NULL,
    verbose_name="OS Distribution",
    related_name="distro"
  )
  osrepos=models.ManyToManyField(
    OSRepo, 
    blank=True,
    verbose_name="Extra OS Repositories"
  )
  class Meta:
    ordering = ['name']
    verbose_name = 'System Image'

  def __str__(self):
    return self.name

# emits jobs to update dns, dhcp, and pxe config if a 
# system or NIC is changed.
# TODO: add the sender information to the
# job params? Or should we just rebuild it all.

@receiver(pre_save, sender=System)
@receiver(pre_save, sender=NetworkInterface)
@receiver(pre_save, sender=SystemBMC)
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
      if type(request.user) == AnonymousUser:
          instance.created_by = User.objects.get(pk=1)
      else:
        instance.created_by = request.user

      
  for slug in ['pxe-update', 'dns-update', 'dhcp-update']:
    JobType = None
    try:
        JobType = JobModule.objects.get(slug=slug)
    except:
        JobType = None
    # print(JobType)
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
  # print(jobservers)
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
  import inspect
  for frame_record in inspect.stack():
      if frame_record[3]=='get_response':
          request = frame_record[0].f_locals['request']
          break
  else:
      request = None
  if request is not None:
      if type(request.user) == AnonymousUser:
          instance.created_by = User.objects.get(pk=1)
      else:
        instance.created_by = request.user
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
