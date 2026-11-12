from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils.text import slugify
from django.dispatch import receiver
from django.db.models.signals import pre_save, pre_delete
from jobqueue.models import JobModule, JobStatus, Job, requeue_job, queue_dnsmasq_jobs, changes_fields
from django.contrib.auth.models import AnonymousUser, User
from django.utils import timezone


class NetworkType(models.Model):
  """ This is where the mPCC will keep track of the physical network types.  Some are prepopulated at install, but you can always add more.
  """
  endpoint="/networktypes/"
  name=models.CharField(max_length=120)
  slug=models.SlugField(unique=True,blank=True,verbose_name="Network Type ID",editable=False)
  #id=models.IntegerField(unique=True, primary_key=False)
  description=models.TextField(blank=True, null=True)
  class Meta:
    verbose_name="Network Type"
  def __str__(self):
    return self.name
  def save(self, *args, **kwargs):
    if not self.slug:
      self.slug = slugify(self.name)
    super().save(*args, **kwargs)


class Network(models.Model):
  """ This is where you will create the logical IP networks that the mPCC should know about and possibly manage."""
  endpoint="/networks/"
  name=models.CharField(max_length=120)
  slug=models.SlugField(unique=True,blank=True,verbose_name="Network ID")
  net_type=models.ForeignKey(
    NetworkType, 
    on_delete=models.CASCADE, 
    verbose_name="Network Type",
    
  )
  
  vlan=models.IntegerField(default=0)
  subnet=models.GenericIPAddressField(default='0.0.0.0')
  masks = []
  for mask in range(1,32):
    masks.append((mask,mask))
  netmask=models.IntegerField(choices=masks, verbose_name="CIDR Mask")
  gateway=models.GenericIPAddressField(blank=True,null=True)
  nameserver1=models.GenericIPAddressField(blank=True,null=True, verbose_name="Primary Nameserver")
  # Add domain
  domain=models.CharField(max_length=255,blank=True,verbose_name="Domain Name")

  # Add Enable DHCP?
  isdhcp = models.BooleanField(default=False, verbose_name="Enable DHCP Server?")

  # Add Enable DNS?
  managedns = models.BooleanField(default=False, verbose_name="Manage DNS?")
  
  # Add Enable Network Booting?
  isbootable = models.BooleanField(default=False, verbose_name="Enable Network Booting?")

  # dhcp net dynamic start
  dhcpstart = models.GenericIPAddressField(blank=True, null=True, verbose_name="DHCP Range Start")
  dhcpend = models.GenericIPAddressField(blank=True, null=True, verbose_name="DHCP Range End")

  def __str__(self):
      return self.name

  def save(self, *args, **kwargs):
    if not self.slug:
      self.slug = slugify(self.name)
    super().save(*args, **kwargs)
  
 

# an InfiniBand GUID (#566): a switch's node GUID or an HCA port's GUID,
# stored lowercase, e.g. 0x506b4b0300abcdef
GUID_VALIDATOR = RegexValidator(r'^0[xX][0-9a-fA-F]{16}$', "Enter a GUID: 0x and 16 hex digits, e.g. 0x506b4b0300abcdef.")

def normalize_guid(value):
  """ A GUID as stored: lowercase, or None when empty (the column is unique, so
  an empty value must be NULL). """
  return value.strip().lower() or None if value else None

def guid_field(verbose_name):
  return models.CharField(max_length=19, null=True, blank=True, unique=True, validators=[GUID_VALIDATOR],
                          verbose_name=verbose_name)


class Switch(models.Model):
  """ This is where you would define the switches that the mPCC should know about for handling Node Auto Detection."""
  endpoint="/switches/"
  # unique (#566): N.A.D.S. matches a booting node's switch by hostname
  hostname=models.CharField(max_length=255, unique=True, verbose_name="Host Name")
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
  network=models.ForeignKey(Network, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Management Network')
  # optional (#566): an unmanaged InfiniBand switch has neither
  mgmt_ip=models.GenericIPAddressField(null=True, blank=True, verbose_name="Management IP")
  mgmt_mac=models.CharField(max_length=100, null=True, blank=True, verbose_name="Management MAC")
  guid=guid_field("InfiniBand GUID")
  class Meta:
    verbose_name = "Switch"
    verbose_name_plural = "Switches"

  def clean(self):
    self.guid = normalize_guid(self.guid)

  def save(self, *args, **kwargs):
    self.guid = normalize_guid(self.guid)
    self.mgmt_mac = self.mgmt_mac or None
    super().save(*args, **kwargs)
  

class SwitchPort(models.Model):
  endpoint="/switchports/"
  name=models.CharField(max_length=100)
  switch=models.ForeignKey(Switch, on_delete=models.CASCADE)
  def __str__(self):
    return "%s/%s" % (self.switch.hostname, self.name)
  networks=models.ForeignKey(Network, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Network')
  class Meta:
    verbose_name = 'Switch Port'  
   
@receiver(pre_save, sender=Switch)
def UpdateSwitch(sender, instance, **kwargs):
  ''' Before a switch is saved: record who saved it (see stamp_users). '''
  from common.request import stamp_users
  stamp_users(instance)

# What the job servers' dnsmasq plugin reads from a switch, through the
# /switches/ list: they put its management MAC and IP in their DHCP and DNS
# config (#547), for the switch's network.
SWITCH_DNSMASQ_FIELDS = ('hostname', 'mgmt_ip', 'mgmt_mac', 'network')

def switch_in_dnsmasq(switch):
  """ Whether the job servers write anything for this switch: only with a
  management IP or MAC (#566). """
  return bool(switch.mgmt_ip or switch.mgmt_mac)

@receiver(pre_save, sender=Switch)
def QueueSwitchJobs(sender, instance, update_fields=None, **kwargs):
  ''' Before a switch is saved, queue the pxe-update, dns-update and
  dhcp-update jobs (see queue_dnsmasq_jobs) only if that changes the job
  servers' config (#566): a new switch with a management IP or MAC, or a
  change to a field in SWITCH_DNSMASQ_FIELDS.  Nodes create switches without
  either as they boot, which mustn't queue a rebuild each. '''
  if instance._state.adding or instance.pk is None:
    if switch_in_dnsmasq(instance):
      queue_dnsmasq_jobs()
  elif changes_fields(instance, SWITCH_DNSMASQ_FIELDS, update_fields):
    queue_dnsmasq_jobs()

@receiver(pre_delete, sender=Switch)
def QueueSwitchDeleteJobs(sender, instance, **kwargs):
  ''' Before a switch is deleted, always queue the same jobs: besides its own
  entry, deleting its ports can move NICs to another network (a port's
  network comes first), without a NIC save to queue them. '''
  queue_dnsmasq_jobs()

# What the job servers' dnsmasq plugin reads from a network, through the
# /networks/ list (#546).
DNSMASQ_FIELDS = ('slug', 'subnet', 'netmask', 'gateway', 'nameserver1', 'domain',
                  'isdhcp', 'managedns', 'dhcpstart', 'dhcpend')

@receiver(pre_save, sender=Network)
def UpdateNetwork(sender, instance, update_fields=None, **kwargs):
  ''' Before a network is saved, queue the pxe-update, dns-update and
  dhcp-update jobs (see queue_dnsmasq_jobs) if it's new or a field in
  DNSMASQ_FIELDS changes. '''
  if changes_fields(instance, DNSMASQ_FIELDS, update_fields):
    queue_dnsmasq_jobs()

@receiver(pre_delete, sender=Network)
def DeleteNetwork(sender, instance, **kwargs):
  for slug in ['pxe-delete', 'dns-delete', 'dhcp-delete']:
    JobType = None
    try:
        JobType = JobModule.objects.get(slug=slug)
    except JobModule.DoesNotExist:
        JobType = None
    # look up the pxe/dns/dhcp-delete job module in the DB
    # get the jobtype, do nothing if it's not defined.
    if JobType is not None:
        # save a new job, if one doesn't already exist.

        requeue_job(JobType)      
