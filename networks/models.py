from django.conf import settings
from django.db import models
from django.utils.text import slugify
from django.dispatch import receiver
from django.db.models.signals import pre_save, pre_delete
from jobqueue.models import JobModule, JobStatus, Job
from django.contrib.auth.models import AnonymousUser, User


class NetworkType(models.Model):
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
  name=models.CharField(max_length=120)
  slug=models.SlugField(unique=True,blank=True,verbose_name="Network ID")
  net_type=models.ForeignKey(
    NetworkType, 
    on_delete=models.CASCADE, 
    verbose_name="Network Type",
    
  )
  
  vlan=models.CharField(max_length=100,default='default')
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
  managedns = models.BooleanField(default=False, verbose_name="Manage DNS for network?")
  
  # Add Enable Network Booting?
  isbootable = models.BooleanField(default=False, verbose_name="Enable network booting?")

  # dhcp net dynamic start
  dhcpstart = models.GenericIPAddressField(blank=True, null=True, verbose_name="DHCP Range Start")
  dhcpend = models.GenericIPAddressField(blank=True, null=True, verbose_name="DHCP Range End")

  def __str__(self):
      return self.name

  def save(self, *args, **kwargs):
    if not self.slug:
      self.slug = slugify(self.name)
    super().save(*args, **kwargs)
  
 

class Switch(models.Model):
  hostname=models.CharField(max_length=255, verbose_name="Host Name")
  timestamp=models.DateTimeField(auto_now_add=True, verbose_name="Created")
  created_by=models.ForeignKey(
    settings.AUTH_USER_MODEL, 
    on_delete=models.SET(1),
    verbose_name="Created By"
  )
  updated=models.DateTimeField(auto_now=True, verbose_name="Last Updated")
  network=models.ForeignKey(Network, on_delete=models.DO_NOTHING, null=True, blank=True, verbose_name='Management\nNetwork')
  mgmt_ip=models.GenericIPAddressField(verbose_name="Management IP")
  mgmt_mac=models.CharField(max_length=100, verbose_name="Management MAC")
  class Meta:
    verbose_name = "Switch"
    verbose_name_plural = "Switches"
  

class SwitchPort(models.Model):
  name=models.CharField(max_length=100)
  switch=models.ForeignKey(Switch, on_delete=models.CASCADE)
  def __str__(self):
    return "%s/%s" % (self.switch.hostname, self.name)
  networks=models.ForeignKey(Network, on_delete=models.DO_NOTHING, null=True, blank=True, verbose_name='Network')
  class Meta:
    verbose_name = 'Switch Port'  
   
@receiver(pre_save, sender=Switch)
def UpdateSwitch(sender, instance, **kwargs):
  if sender == Switch:
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
@receiver(pre_save, sender=Network)
def UpdateNetwork(sender, instance, **kwargs):

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

@receiver(pre_delete, sender=Network)
def DeleteNetwork(sender, instance, **kwargs):
  for slug in ['pxe-delete', 'dns-delete', 'dhcp-delete']:
    JobType = None
    try:
        JobType = JobModule.objects.get(slug=slug)
    except:
        JobType = None
    print(JobType)
    # get or create the job module in the DB
    # get the jobtype, do nothing if it's not defined.
    if JobType is not None:
        # save a new job, if one doesn't already exist.

        Job.objects.update_or_create(
          name=JobType.name , module=JobType,
          defaults={'status': JobStatus.objects.get(pk=1)}
        )      
