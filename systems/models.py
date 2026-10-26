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
from scripts.models import Script, AnsiblePlaybook, AnsibleRole, AnsibleCollection
from django.contrib.auth.models import AnonymousUser, User
from django.utils import timezone

class SystemGroup(models.Model):
  """ System Groups are ways to group systems and system images together to manage configuration better.   You can specify configuration
  options and parameters at the system group level that will override anything set at the OS Distro level and be overridden by anything at
  the system level.  """
  name=models.CharField(max_length=255)
  scripts = models.ManyToManyField(Script, blank=True, )
  ansibleplaybooks = models.ManyToManyField(AnsiblePlaybook, blank=True, verbose_name="Ansible Playbooks")
  ansibleroles = models.ManyToManyField(AnsibleRole, blank=True, verbose_name="Ansible Roles")
  ansiblecollections = models.ManyToManyField(AnsibleCollection, blank=True, verbose_name="Ansible Collections" )
  install_kernel_cmdline=models.CharField(max_length=4096, default="",help_text="Options to pass to the install kernel", blank=True)
  # install kernel parameters.
  tmpfs_root_size = models.IntegerField(default=0, help_text="Size of the root tmpfs filesystem in Gigabytes, 0 inherits from parent Group/Distro")
  initial_mods = models.CharField(default="", help_text="Comma-separated list of modules to load.", max_length=255, blank=True)
  prov_interface = models.CharField(default="", help_text="Interface name to provision over.", max_length=255, blank=True)
  systems = models.ManyToManyField("System", blank=True)
  

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
  """ System Models are used as part of the NADS (Node Auto Detection System).  The Vendor and Model strings should match what comes out
  of dmidecode so that the system can identify itself to the mPCC as a valid host.
  """
  slug = models.SlugField(primary_key=True, blank=True )
  name = models.CharField(verbose_name="Model Name", max_length=255)
  vendor = models.CharField(verbose_name="Vendor Name", max_length=255)

  class Meta:
    verbose_name = "System Model"
    verbose_name_plural = "System Models"

  def __str__(self) -> str:
     return f"{self.vendor}/{self.name}"

  def save(self, *args, **kwargs):
    if not self.slug:
      self.slug = slugify(f"{self.vendor} {self.name}")
    super(SystemModel, self).save(*args, **kwargs)


def has_content(value):
  """ True if value has a line that isn't blank or a # comment, so an
  inherited field set to only comments doesn't override the layer below. """
  return any(line.strip() and not line.lstrip().startswith("#") for line in value.split("\n"))

class System(models.Model):
  """ Systems are physical or virtual machines that will run an OS in RAM or have an OS installed on them.  This is the endpoint for the mPCC's
  provisioning system."""
  endpoint="/systems/"
  hostname=models.CharField(max_length=255, verbose_name="Host Name")
  timestamp=models.DateTimeField(default=timezone.now, verbose_name="Created")
  created_by=models.ForeignKey(
    settings.AUTH_USER_MODEL, 
    on_delete=models.SET(1),
    verbose_name="Created By"
  )
  updated=models.DateTimeField(default=timezone.now, verbose_name="Last Updated")
  systemgroups = models.ManyToManyField(SystemGroup, verbose_name="System Groups",blank=True, through=SystemGroup.systems.through)
  scripts = models.ManyToManyField(Script, blank=True, )
  ansibleplaybooks = models.ManyToManyField(AnsiblePlaybook, blank=True, verbose_name="Ansible Playbooks")
  ansibleroles = models.ManyToManyField(AnsibleRole, blank=True, verbose_name="Ansible Roles")
  ansiblecollections = models.ManyToManyField(AnsibleCollection, blank=True, verbose_name="Ansible Collections" )
    
  config_params = models.TextField(
    default="# Inherit from System Group or Distribution.",
    verbose_name="Configuration Parameters",
    blank=True,
    null=True,
  )
  install_kernel_cmdline=models.CharField(max_length=4096, default="",help_text="Options to pass to the install kernel", blank=True)
  # install kernel parameters.
  tmpfs_root_size = models.IntegerField(default=0, help_text="Size of the root tmpfs filesystem in Gigabytes, 0 inherits from parent Group/Distro")
  initial_mods = models.CharField(default="", help_text="Comma-separated list of modules to load.", max_length=255, blank=True)
  prov_interface = models.CharField(default="", help_text="Interface name to provision over.", max_length=255, blank=True)

  systemimage = models.ForeignKey('SystemImage', blank=True, null=True, on_delete=models.SET_NULL, verbose_name="System Image")
  systemmodel = models.ForeignKey('SystemModel', blank=True, null=True, on_delete=models.SET_NULL, verbose_name="System Model")
  disks = models.ManyToManyField('disklayouts.Disklayout', blank=True, through=DiskLayout.systems.through)
  # bootdisk = models.ForeignKey(DiskLayout, blank=True, null=True, on_delete=models.SET_NULL, verbose_name="Boot Disk Layout", help_text="Boot disk layout for stateful installs")
  stateful = models.BooleanField(default=False, verbose_name="Stateful System?", help_text="Should this system install its image to disk?")
  location = models.ForeignKey('SystemLocation', blank=True, null=True, on_delete=models.SET_NULL,  )
  provision = models.BooleanField(default=True, verbose_name="Provision?", help_text="Should this system be provisioned (installed or netbooted) on its next PXE boot? The stateful installer clears this once it has installed.")
  class Meta:
    ordering = ['hostname']
    verbose_name = 'System'
    verbose_name_plural = 'Systems'
  
  inheritableFields=['install_kernel_cmdline', 'tmpfs_root_size', 'initial_mods', 'prov_interface', 'config_params']

  def __str__(self):
    return self.hostname

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.flatten_config()

  def enable_provisioning(self):
    """ Set provision so the next PXE boot provisions this system.  Returns
    False, and changes nothing, if the system has no bootable NIC to boot from. """
    if not NetworkInterface.objects.filter(system=self, bootable=True).exists():
      return False
    if not self.provision:
      self.provision = True
      self.save()
    return True

  
  def flatten_config(self):
    # rebuilt per instance on every call, never shared between Systems.
    self.config = {}
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
              if type(sysgrpfield) is str:
                if sysgrpfield != "" :
                  if has_content(sysgrpfield):
                    if field == 'install_kernel_cmdline' or field == 'initial_mods':
                      if sysgrpfield[0] == "=":
                        # user is asking us to overwrite the field here.
                        self.config[field] = sysgrpfield[1:]
                      else:
                        # no specifier, let's append
                        if field == 'install_kernel_cmdline':
                          # kernel cmdline is space separated.
                          self.config[field] = (self.config.get(field, "") + f" {sysgrpfield}").lstrip(" ")
                        else:
                          # mod list is comma separated.
                          self.config[field] = (self.config.get(field, "") + f",{sysgrpfield}").lstrip(",")
                    else: 
                      # everything else overwrites.
                      self.config[field] = sysgrpfield
              elif type(sysgrpfield) is int:
                if sysgrpfield != 0:
                  self.config[field] = sysgrpfield
          
    # finally see if the object has it set on its top level and overwrite it to the
    # config dict.
    for field in self._meta.get_fields():
      field = field.name
      if field in self.inheritableFields:
        # system attr are highest inheritance
        sysfield = getattr(self, field)
        if type(sysfield) is str:
          if sysfield != "" :
            if has_content(sysfield):
              if field == 'install_kernel_cmdline' or field == 'initial_mods':
                if sysfield[0] == "=":
                  # user is asking us to overwrite the field here.
                  self.config[field] = sysfield[1:]
                else:
                  # no specifier, let's append
                  if field == 'install_kernel_cmdline':
                    # kernel cmdline is space separated.
                    self.config[field] = (self.config.get(field, "") + f" {sysfield}").lstrip(" ")
                  else:
                    # mod list is comma separated.
                    self.config[field] = (self.config.get(field, "") + f",{sysfield}").lstrip(",")
              else: 
                # everything else overwrites.
                self.config[field] = sysfield
        elif type(sysfield) is int:
          if sysfield != 0:
            
            self.config[field] = sysfield

class SystemBMC(models.Model):
  endpoint="/systembmcs/"
  system = models.ForeignKey(System, on_delete=models.CASCADE)
  ipaddress=models.GenericIPAddressField(verbose_name="IP Address")
  mac=models.CharField(max_length=100, verbose_name="MAC Address", blank=True, null=True)
  username=models.CharField(max_length=255, verbose_name="BMC User", blank=True, null=True)
  password=models.CharField(max_length=100, verbose_name="BMC Password", blank=True, null=True)
  switch_port=models.ForeignKey(SwitchPort, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Switch Port")
  network=models.ForeignKey(Network, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Network")
  ipv6ll=models.GenericIPAddressField(verbose_name="IPv6 LL Address", blank=True, null=True)
  vlan=models.IntegerField(verbose_name='VLAN ID', default=0)
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
    return self.cleaned_data

class NetworkInterface(models.Model):
  endpoint="/networkinterfaces/"
  system = models.ForeignKey(System, on_delete=models.CASCADE)
  name=models.CharField(max_length=50, verbose_name="Iface. Name",)
  hostname=models.CharField(max_length=255, blank=True, null=True)
  hostaliases=models.CharField(max_length=4096, help_text="A space-separated list of alternate hostnames.", null=True, blank=True)
  ipaddress=models.GenericIPAddressField(verbose_name="IP Address", blank=True, null=True)
  isgateway=models.BooleanField(verbose_name="Gateway NIC?", default=True)
  ipv6ll=models.GenericIPAddressField(verbose_name="IPv6 LL Address", blank=True, null=True)
  mtu = models.IntegerField(verbose_name="MTU", default=1500)
  mac=models.CharField(max_length=100, verbose_name="MAC Address", blank=True, null=True)
  switch_port=models.OneToOneField(SwitchPort, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Switch Port")
  network=models.ForeignKey(Network, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Network")
  bootable=models.BooleanField(default=False,null=True, blank=True)
  ipv6gua=models.GenericIPAddressField(verbose_name="IPv6 SLAAC GUA", blank=True, null=True)

  def __str__(self):
    return self.name
  def save(self, *args, **kwargs):
    self.hostname = self.system.hostname
    super(NetworkInterface, self).save(*args, **kwargs)
    if self.bootable:
      # a system boots from at most one NIC.
      NetworkInterface.objects.filter(system=self.system, bootable=True).exclude(pk=self.pk).update(bootable=False)

class SystemImage(models.Model):
  """ System Images are filesystems that are managed by the mPCC's configuration management, built into .img files, and synced out to Systems."""
  endpoint="/systemimages/"
  name=models.CharField(max_length=255, verbose_name="Image Name",unique=True,)
  slug=models.SlugField(max_length=255, unique=True, editable=False, verbose_name='Image ID', primary_key=True)
  timestamp=models.DateTimeField(default=timezone.now, verbose_name="Created")
  created_by=models.ForeignKey(
    settings.AUTH_USER_MODEL, 
    on_delete=models.SET(1),
    verbose_name="Created By",
  )
  updated=models.DateTimeField(default=timezone.now, verbose_name="Last Updated")
  systemgroups = models.ManyToManyField(SystemGroup, verbose_name="System Groups",blank=True)
  scripts = models.ManyToManyField(Script, blank=True, default="install_mprov_script_runner_sh")
  ansibleplaybooks = models.ManyToManyField(AnsiblePlaybook, blank=True, verbose_name="Ansible Playbooks")
  ansibleroles = models.ManyToManyField(AnsibleRole, blank=True, verbose_name="Ansible Roles")
  ansiblecollections = models.ManyToManyField(AnsibleCollection, blank=True, verbose_name="Ansible Collections" )
  
  needs_rebuild = models.BooleanField(default=True, verbose_name="Rebuild Image?")
  version = models.BigIntegerField(default=1, verbose_name="Image Version")
  jobservers = models.ManyToManyField(JobServer, verbose_name="Hosted By", blank=True)
  config_params = models.TextField(
    default="# Inherit from System Group or Distribution.",
    verbose_name="Configuration Parameters",
    blank=True,
    null=True,
  )
  customIPXE = models.TextField(
    verbose_name="Custom iPXE Script",
    help_text="Leave blank to use the iPXE script mProv generates. Any text here is served instead of it, and job servers won't register as hosts of this image.",
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

class NADSSystem(models.Model):
  mac=models.CharField(max_length=100, verbose_name="MAC Address", unique=True)
  discovered=models.DateTimeField(default=timezone.now, verbose_name="Discovered")
  system=models.ForeignKey(System, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Assign System")
  switch=models.CharField(max_length=1024, verbose_name="Detected Switch", null=True, blank=True,)
  port=models.CharField(max_length=1024, verbose_name="Detected Port", null=True, blank=True,)
  vendor=models.CharField(max_length=1024, verbose_name="Detected Vendor", null=True, blank=True,)
  model=models.CharField(max_length=1024, verbose_name="Detected Model",  null=True, blank=True,)
  serial=models.CharField(max_length=1024, verbose_name="Serial Number", null=True, blank=True,)
  def __str__(self):
    return self.mac

  class Meta:
    verbose_name="N.A.D.S. Discovered"
    verbose_name_plural="N.A.D.S. Discovered"

class SystemLocation(models.Model):
  slug=models.SlugField(max_length=255, unique=True, editable=False, verbose_name='Location ID', primary_key=True)
  name=models.CharField(verbose_name="Name", max_length=1024)
  address=models.CharField(max_length=1024, null=True, blank=True, )
  building=models.CharField(max_length=1024, null=True, blank=True, )
  room=models.CharField(max_length=1024, null=True, blank=True, )
  rack=models.CharField(max_length=1024, null=True, blank=True, )
  def __str__(self):
    return self.name
  class Meta:
    verbose_name="System Location"
  def save(self, *args, **kwargs):
    if not self.slug:
      self.slug = slugify(f"{self.name}")
    super(SystemLocation, self).save(*args, **kwargs)
  
@receiver(post_save, sender=NADSSystem)
def AssignSystem(sender, instance, **kwargs):
  if instance.system is not None:
    # Save the MAC to the interface marked as bootable on the system 
    sysnic = NetworkInterface.objects.all()
    sysnic = sysnic.filter(system=instance.system, bootable=True)
    if sysnic.count() == 0:
      print("Error: No bootable NIC found.")
      return
    sysnic = sysnic[0]
    sysnic.mac=instance.mac
    sysnic.save()
    instance.delete()
    
@receiver(post_save, sender=System)
@receiver(post_save, sender=SystemImage)
@receiver(post_save, sender=SystemGroup)
def UpdateGenders (sender, instance, **kwargs):
  JobType = None
  try:
      JobType = JobModule.objects.get(slug="libgenders")
  except JobModule.DoesNotExist:
      JobType = None
  if JobType is not None:
    # save a new job, if one doesn't already exist.

    Job.objects.update_or_create(
      name=JobType.name , module=JobType,
      defaults={'status': JobStatus.objects.get(pk=1)}
    )

# emits jobs to update dns, dhcp, and pxe config if a
# system, NIC, or BMC is changed.
# TODO: add the sender information to the
# job params? Or should we just rebuild it all.

@receiver(pre_save, sender=System)
@receiver(pre_save, sender=NetworkInterface)
@receiver(pre_save, sender=SystemBMC)
def UpdateSystemAttributes(sender, instance, **kwargs):
  
  # SystemImage isn't a sender here; UpdateSystemImages sets its created_by.
  if sender == System:
    import inspect
    for frame_record in inspect.stack():
        if frame_record[3]=='get_response':
            request = frame_record[0].f_locals['request']
            break
    else:
        request = None
    if request is not None:
      if type(request.user) is AnonymousUser:
          instance.created_by = User.objects.get(pk=1)
      else:
        instance.created_by = request.user

      
  for slug in ['pxe-update', 'dns-update', 'dhcp-update']:
    JobType = None
    try:
        JobType = JobModule.objects.get(slug=slug)
    except JobModule.DoesNotExist:
        JobType = None
    # look up the pxe/dns/dhcp update job module in the DB
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
  # now clear this so everyone stops serving it.
  instance.jobservers.clear()


  JobType = None
  try:
      JobType = JobModule.objects.get(slug='image-delete')
  except JobModule.DoesNotExist:
      JobType = None
  # get the jobtype, do nothing if it's not defined.
  if JobType is not None:
    # submit an image-delete job for every jobserver in
    # the list of jobservers this image is hosted on
    params = { 'imageId': instance.slug}
    for jobserver in jobservers:
      Job.objects.create( name=JobType.name, 
        module=JobType, 
        status=JobStatus.objects.get(pk=1), 
        params = params,
        jobserver = jobserver,
      )
  else:
    print("WARN: No image-delete job module found; no job was queued.")

# emits an image-update job every time an image is saved with needs_rebuild set.
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
      if type(request.user) is AnonymousUser:
          instance.created_by = User.objects.get(pk=1)
      else:
        instance.created_by = request.user
  instance.slug = slugify(instance.name)
  if not instance.needs_rebuild:
    return
  JobType = None
  try:
      JobType = JobModule.objects.get(slug='image-update')
  except JobModule.DoesNotExist:
      JobType = None

  # get the jobtype, do nothing if it's not defined.
  if JobType is not None:

      # create a new image-update job.
      params = { 'imageId': instance.slug, 'origin': 'pre_save'}
      Job.objects.create( name=JobType.name, 
          module=JobType, 
          status=JobStatus.objects.get(pk=1), 
          params = params,
      )

      # Increment version number and clear out jobservers field.
      instance.jobservers.clear()
      instance.version = instance.version + 1
      instance.needs_rebuild = False
