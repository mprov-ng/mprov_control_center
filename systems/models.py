from django.db import models, transaction
from django.conf import settings
from django.dispatch import receiver
from django.forms import CharField, PasswordInput, ModelForm
from disklayouts.models import DiskLayout
from networks.models import SwitchPort, Network
from osmanagement.models import OSDistro, OSRepo
from django.db.models.signals import pre_save, pre_delete, post_save
from jobqueue.models import JobModule, JobStatus, Job, JobServer, requeue_job, queue_dnsmasq_jobs, changes_fields
from django.utils.text import slugify
from scripts.models import Script, AnsiblePlaybook, AnsibleRole, AnsibleCollection, File
from django.contrib.auth.models import AnonymousUser, User
from django.utils import timezone
from django.utils.functional import cached_property
from common import render_config, flat_config
from common.request import stamp_users
import logging

# serial number changes (#60), e.g. "serial: c01 changed ABC123 -> XYZ789 (node)".
serial_log = logging.getLogger('mprov.serial')

# What dmidecode / /sys/class/dmi/id/product_serial report on boards and VMs
# with no real serial number.  Compared case-insensitively; they're ignored,
# so a placeholder never overwrites a real serial.
SERIAL_PLACEHOLDERS = {
  "", "0", "none", "n/a", "na", "null", "not specified", "not applicable", "not available",
  "to be filled by o.e.m.", "to be filled by oem", "system serial number", "default string",
  "chassis serial number", "serial number", "0123456789", "123456789", "xxxxxxxxxx",
}

def clean_serial(value):
  ''' value with surrounding whitespace removed, or None if it's empty or a
  placeholder (see SERIAL_PLACEHOLDERS). '''
  if value is None:
    return None
  value = str(value).strip()
  if value.lower() in SERIAL_PLACEHOLDERS:
    return None
  return value

class SystemGroup(models.Model):
  """ System Groups are ways to group systems and system images together to manage configuration better.   You can specify configuration
  options and parameters at the system group level that will override anything set at the OS Distro level and be overridden by anything at
  the system level.  """
  name=models.CharField(max_length=255)
  scripts = models.ManyToManyField(Script, blank=True, )
  ansibleplaybooks = models.ManyToManyField(AnsiblePlaybook, blank=True, verbose_name="Ansible Playbooks")
  ansibleroles = models.ManyToManyField(AnsibleRole, blank=True, verbose_name="Ansible Roles")
  ansiblecollections = models.ManyToManyField(AnsibleCollection, blank=True, verbose_name="Ansible Collections" )
  files = models.ManyToManyField(File, blank=True, verbose_name="Managed Files", help_text="Files placed into the images built from this.")
  install_kernel_cmdline=models.CharField(max_length=4096, default="",help_text="Options to pass to the install kernel, added after the inherited ones. Start with = to replace the inherited options instead.", blank=True)
  # install kernel parameters.
  tmpfs_root_size = models.IntegerField(default=0, help_text="Size of the root tmpfs filesystem in Gigabytes, 0 inherits from parent Group/Distro")
  initial_mods = models.CharField(default="", help_text="Comma-separated list of modules to load, added after the inherited ones. Start with = to replace the inherited list instead.", max_length=255, blank=True)
  prov_interface = models.CharField(default="", help_text="Interface name to provision over.", max_length=255, blank=True)
  systems = models.ManyToManyField("System", blank=True)
  

  endpoint="/systemgroups/"
  config_params=models.TextField(
    blank=True, 
    default="# Inherit from OS", 
    verbose_name="Configuration Parameters",
    help_text="YAML. Merged with the inherited parameters by top-level key: a key set here replaces that key's whole inherited value. Only comments means inherit.",
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
  # who saved it last during a request; created_by is who created it.
  updated_by=models.ForeignKey(
    settings.AUTH_USER_MODEL, null=True, blank=True, editable=False,
    on_delete=models.SET_NULL, related_name='+', verbose_name="Updated By"
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
    help_text="YAML. Merged with the inherited parameters by top-level key: a key set here replaces that key's whole inherited value. Only comments means inherit.",
    blank=True,
    null=True,
  )
  install_kernel_cmdline=models.CharField(max_length=4096, default="",help_text="Options to pass to the install kernel, added after the inherited ones. Start with = to replace the inherited options instead.", blank=True)
  # install kernel parameters.
  tmpfs_root_size = models.IntegerField(default=0, help_text="Size of the root tmpfs filesystem in Gigabytes, 0 inherits from parent Group/Distro")
  initial_mods = models.CharField(default="", help_text="Comma-separated list of modules to load, added after the inherited ones. Start with = to replace the inherited list instead.", max_length=255, blank=True)
  prov_interface = models.CharField(default="", help_text="Interface name to provision over.", max_length=255, blank=True)

  systemimage = models.ForeignKey('SystemImage', blank=True, null=True, on_delete=models.SET_NULL, verbose_name="System Image")
  systemmodel = models.ForeignKey('SystemModel', blank=True, null=True, on_delete=models.SET_NULL, verbose_name="System Model")
  disks = models.ManyToManyField('disklayouts.Disklayout', blank=True, through=DiskLayout.systems.through)
  # bootdisk = models.ForeignKey(DiskLayout, blank=True, null=True, on_delete=models.SET_NULL, verbose_name="Boot Disk Layout", help_text="Boot disk layout for stateful installs")
  stateful = models.BooleanField(default=False, verbose_name="Stateful System?", help_text="Should this system install its image to disk?")
  location = models.ForeignKey('SystemLocation', blank=True, null=True, on_delete=models.SET_NULL,  )
  provision = models.BooleanField(default=True, verbose_name="Provision?", help_text="Should this system be provisioned (installed or netbooted) on its next PXE boot? The stateful installer clears this once it has installed.")
  last_booted = models.DateTimeField(null=True, blank=True, editable=False, verbose_name="Last Booted", help_text="When the system last reported that it had booted.")
  serial = models.CharField(max_length=255, null=True, blank=True, verbose_name="Serial Number", help_text="Reported by the node at boot, or by N.A.D.S.; set it here to correct it.  Each change is kept in the serial history.")
  class Meta:
    ordering = ['hostname']
    verbose_name = 'System'
    verbose_name_plural = 'Systems'
  
  def __str__(self):
    return self.hostname

  def set_serial(self, value, source):
    ''' Set this system's serial number as reported by a node or N.A.D.S.
    (source "node" or "nads"), recording the change in its serial history.
    A placeholder or empty value is ignored, so it never wipes a real serial.
    Saved with a queryset update, so a node reporting its serial doesn't
    queue the dns/dhcp/pxe/genders jobs a System save does.  Returns True if
    the serial changed. '''
    new = clean_serial(value)
    if new is None:
      return False
    new = new[:255]
    old = self.serial or None
    if new == old:
      return False
    with transaction.atomic():
      System.objects.filter(pk=self.pk).update(serial=new)
      self.serial = new
      self.record_serial_change(old, new, source)
    return True

  def record_serial_change(self, old, new, source, user=None):
    ''' Record a change of this system's serial number, already saved, in
    its serial history and the log.  Does nothing if it didn't change. '''
    old, new = old or None, new or None
    if old == new:
      return
    SystemSerialHistory.objects.create(system=self, old_serial=old, new_serial=new, source=source,
                                       changed_by=user if getattr(user, "pk", None) else None)
    serial_log.info(f"serial: {self.hostname} changed {old or '-'} -> {new or '-'} ({source})")

  def save(self, *args, **kwargs):
    # Each NIC carries a copy of the hostname (NetworkInterface.save()), which
    # DHCP/DNS and register_IPv6_ll.py read.  Update the copies in the same
    # transaction, so a rename never leaves NICs with the old name (#382).
    # The pre_save signal below already queues the dns/dhcp/pxe jobs.
    with transaction.atomic():
      super().save(*args, **kwargs)
      NetworkInterface.objects.filter(system=self).exclude(hostname=self.hostname).update(hostname=self.hostname)

  @cached_property
  def config(self):
    """ This system's config, merged from its OS distro, system groups, image
    and itself by common.render_config(). """
    if self.id is None:
      return {}
    return flat_config(render_config(self))

  def boot_disk_problem(self):
    """ Why the stateful installer would refuse this system's disk layouts, or
    None.  Like buildDisks() in static/mprov_stateful.py, it needs exactly one
    disk layout with a bootable partition, across all the system's layouts. """
    if not self.stateful or self.id is None:
      return None
    # by name, so the message is the same on every database backend.
    layouts = list(self.disks.order_by('name'))
    if not layouts:
      return f"{self} is stateful but has no disk layouts, so the stateful installer will fail."
    bootdisks = [layout for layout in layouts if layout.partitions.filter(bootable=True).exists()]
    if not bootdisks:
      return (f"{self} is stateful but none of its disk layouts has a bootable partition, so the stateful "
              "installer will fail.  Mark the partition it boots from as bootable.")
    if len(bootdisks) > 1:
      names = ", ".join(layout.name for layout in bootdisks)
      return (f"{self} is stateful and more than one of its disk layouts has a bootable partition ({names}), "
              "so the stateful installer will fail.  Only the disk it boots from can have one.")
    return None

  def provisioning_problem(self):
    """ Why this system can't be provisioned on its next PXE boot, or None. """
    if not NetworkInterface.objects.filter(system=self, bootable=True).exists():
      return f"{self} has no bootable network interface, so it can't PXE boot."
    return self.boot_disk_problem()

  def enable_provisioning(self):
    """ Set provision so the next PXE boot provisions this system.  Returns
    False, and changes nothing, if provisioning_problem() finds a reason it
    can't be provisioned. """
    if self.provisioning_problem() is not None:
      return False
    if not self.provision:
      self.provision = True
      self.save()
    return True

class SystemSerialHistory(models.Model):
  ''' One change of a system's serial number (#60), e.g. after a board swap. '''
  SOURCES = [
    ("admin", "Admin"),
    ("api", "API"),
    ("nads", "N.A.D.S."),
    ("node", "Node at boot"),
  ]
  system = models.ForeignKey(System, on_delete=models.CASCADE, related_name="serial_history")
  old_serial = models.CharField(max_length=255, null=True, blank=True, verbose_name="Old Serial Number")
  new_serial = models.CharField(max_length=255, null=True, blank=True, verbose_name="New Serial Number")
  changed = models.DateTimeField(default=timezone.now, verbose_name="Changed")
  source = models.CharField(max_length=16, choices=SOURCES, verbose_name="Changed By")
  changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="User", related_name="+")
  class Meta:
    ordering = ['-changed', '-id']
    verbose_name = 'Serial Number Change'
    verbose_name_plural = 'Serial Number History'

  def __str__(self):
    return f"{self.system}: {self.old_serial or '-'} -> {self.new_serial or '-'}"

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
  credentials_changed=models.DateTimeField(null=True, blank=True, editable=False, verbose_name="Credentials Changed",
    help_text="When the BMC username or password stored here last changed.")
  class Meta:
    verbose_name = 'Power Management'
    verbose_name_plural = 'Power Management'

  
  def __str__(self):
    return self.system.hostname + "-bmc"

  def save(self, *args, **kwargs):
    # note when the stored credentials change, from any form or the API (#374).
    old = SystemBMC.objects.filter(pk=self.pk).values('username', 'password').first() if self.pk else None
    if (self.username or self.password) if old is None else \
       (old['username'], old['password']) != (self.username, self.password):
      self.credentials_changed = timezone.now()
      if kwargs.get('update_fields') is not None:
        kwargs['update_fields'] = set(kwargs['update_fields']) | {'credentials_changed'}
    super().save(*args, **kwargs)

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
  # who saved it last during a request; created_by is who created it.
  updated_by=models.ForeignKey(
    settings.AUTH_USER_MODEL, null=True, blank=True, editable=False,
    on_delete=models.SET_NULL, related_name='+', verbose_name="Updated By"
  )
  updated=models.DateTimeField(default=timezone.now, verbose_name="Last Updated")
  systemgroups = models.ManyToManyField(SystemGroup, verbose_name="System Groups",blank=True)
  scripts = models.ManyToManyField(Script, blank=True, default="install_mprov_script_runner_sh")
  ansibleplaybooks = models.ManyToManyField(AnsiblePlaybook, blank=True, verbose_name="Ansible Playbooks")
  ansibleroles = models.ManyToManyField(AnsibleRole, blank=True, verbose_name="Ansible Roles")
  ansiblecollections = models.ManyToManyField(AnsibleCollection, blank=True, verbose_name="Ansible Collections" )
  files = models.ManyToManyField(File, blank=True, verbose_name="Managed Files", help_text="Files placed into the images built from this.")
  
  needs_rebuild = models.BooleanField(default=True, verbose_name="Rebuild Image?")
  version = models.BigIntegerField(default=1, verbose_name="Image Version")
  jobservers = models.ManyToManyField(JobServer, verbose_name="Hosted By", blank=True)
  config_params = models.TextField(
    default="# Inherit from System Group or Distribution.",
    verbose_name="Configuration Parameters",
    help_text="YAML. Merged with the inherited parameters by top-level key: a key set here replaces that key's whole inherited value. Only comments means inherit.",
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

  @cached_property
  def config(self):
    """ This image's config, merged from its OS distro, system groups and
    itself by common.render_config(). """
    if self._state.adding:
      return {}
    return flat_config(render_config(self))

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
  ''' When an admin assigns a N.A.D.S.-discovered entry to a system, give that
  system's bootable NIC the discovered MAC (and the system the discovered
  serial number, #60), then delete the N.A.D.S. entry.  If the system has no
  bootable NIC it prints an error and changes nothing else: the entry stays,
  pointing at the system, and no NIC gets the MAC.
  '''
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
    if instance.serial:
      instance.system.set_serial(instance.serial, "nads")
    instance.delete()
    
@receiver(post_save, sender=System)
@receiver(post_save, sender=SystemImage)
@receiver(post_save, sender=SystemGroup)
def UpdateGenders (sender, instance, **kwargs):
  ''' Queue the libgenders job (one pending job at most, see requeue_job) after
  any save of a system, image or system group, so the job servers'
  genders file is rebuilt.  Nothing is queued if no libgenders job module
  exists.
  '''
  JobType = None
  try:
      JobType = JobModule.objects.get(slug="libgenders")
  except JobModule.DoesNotExist:
      JobType = None
  if JobType is not None:
    # save a new job, if one doesn't already exist.

    requeue_job(JobType)

# What the job servers' dnsmasq plugin reads from each sender, through the
# /networkinterfaces/ and /systembmcs/ lists, to build its DNS, DHCP and PXE
# config.  A system's hostname reaches it as its NICs' copies.  Saving
# anything else (provision, bootable, BMC credentials...) changes nothing
# it builds, so queues nothing (#546).
DNSMASQ_FIELDS = {
  System: ('hostname',),
  NetworkInterface: ('system', 'hostname', 'hostaliases', 'ipaddress', 'ipv6ll', 'mac', 'network'),
  SystemBMC: ('system', 'ipaddress', 'mac', 'network'),
}

@receiver(pre_save, sender=System)
@receiver(pre_save, sender=NetworkInterface)
@receiver(pre_save, sender=SystemBMC)
def UpdateSystemAttributes(sender, instance, update_fields=None, **kwargs):
  ''' Before a system, NIC or BMC is saved, queue the pxe-update, dns-update and
  dhcp-update jobs (one pending job each at most, see requeue_job) for
  whichever of those job modules exist, if the save is new or changes a
  field in DNSMASQ_FIELDS, so the job servers' boot, DNS and DHCP config
  follow the change.  For a system saved during a request, it also records
  the user the request acts as (acting_user): as updated_by always, and as
  created_by when the system is new.
  '''
  # SystemImage isn't a sender here; UpdateSystemImages sets its own.
  if sender == System:
    stamp_users(instance)
  if changes_fields(instance, DNSMASQ_FIELDS[sender], update_fields):
    queue_dnsmasq_jobs()

# emit image-delete jobs for every server that currently 
# hosts a deleted image.
@receiver(pre_delete, sender=SystemImage)
def DeleteSystemImage(sender, instance, **kwargs):
  ''' Before an image is deleted, stop every job server serving it (clear
  jobservers) and queue an image-delete job for each of those job servers,
  so they remove their copy.  Prints a warning, and queues nothing, if there
  is no image-delete job module.
  '''
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
  ''' Before an image is saved: record the user the request acts as (see
  stamp_users), and set the slug (its primary key) from its name.  If
  needs_rebuild is set, queue an image-update job for it, clear its job servers (none serve the
  old build any more), bump its version and clear needs_rebuild, so this
  save records the rebuild having been requested.  Nothing is queued if
  there is no image-update job module.
  '''
  stamp_users(instance)
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
