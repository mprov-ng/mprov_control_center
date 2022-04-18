from django.conf import settings
from django.db import models



class NetworkType(models.Model):
  name=models.CharField(max_length=120)
  description=models.TextField(blank=True, null=True)
  class Meta:
    verbose_name="Network Type"
  def __str__(self):
    return self.name


class Network(models.Model):
  name=models.CharField(max_length=120)
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
  def __str__(self):
      return self.name
  
 

class Switch(models.Model):
  hostname=models.CharField(max_length=255, verbose_name="Host Name")
  domainname=models.CharField(max_length=255, verbose_name="Domain Name")
  timestamp=models.DateTimeField(auto_now_add=True, verbose_name="Created")
  created_by=models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.DO_NOTHING, verbose_name="Created By")
  updated=models.DateTimeField(auto_now=True, verbose_name="Last Updated")
  network=models.ForeignKey(Network, on_delete=models.DO_NOTHING, verbose_name='Management\nNetwork')
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
  networks=models.ManyToManyField(Network, verbose_name='Networks')
  class Meta:
    verbose_name = 'Switch Port'  
   