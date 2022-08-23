from curses.ascii import FF
from urllib import request
from django.db import models
from django.utils.text import slugify

# partitions
# partiion mount point
# size
# fill?
# filesystem
# disklayout

# TODO: 
# Software RAID arrays?
# partiion ID
# mount point
# raid level
# disklayout

class DiskPartition(models.Model):
  partnum = models.IntegerField(default=0, verbose_name="Part. Number")
  mount=models.CharField(verbose_name="Mount Point", max_length=4096, help_text="The directory this partition will mount to or 'raid' if it is a Software RAID member.")
  size=models.BigIntegerField(verbose_name="Size")
  fill=models.BooleanField(default=False, verbose_name="Grow to fill?")
  filesystem=models.CharField(verbose_name="Filesysetm", max_length=255)
  disklayout = models.ForeignKey("DiskLayout", on_delete=models.CASCADE, verbose_name="Associated Layout", related_name='partitions')
  bootable = models.BooleanField("Booable Partition?", default=False)
  
  
  def __str__(self) -> str:
    layout = self.disklayout.slug
    device = self.disklayout.diskname
    partnum = self.partnum
    return f"{layout}-{device}{partnum}"


class DiskLayout(models.Model):
  class Meta:
    verbose_name = "Physical Disk Layout"
  class DiskTypes(models.TextChoices):
    SCSI = 'scsi', 'SCSI Disk'
    NVME = 'nvme', 'NVMe'
    MDRD = 'mdrd', 'Software RAID'

  name = models.CharField(verbose_name="Layout Name", max_length=255)
  diskname = models.CharField(verbose_name="Disk Device", max_length=255)
  slug = models.SlugField(primary_key=True, unique=True, blank=True)
  systems = models.ManyToManyField('systems.System', blank=True, related_name='disklayouts')
  dtype = models.CharField(max_length=4, verbose_name="Disk Type", choices=DiskTypes.choices, default=DiskTypes.SCSI)
  def __str__(self) -> str:
    return self.name



  def save(self, *args, **kwargs):
    if not self.slug:
      self.slug = slugify(self.name)
    print(self.dtype)
    # if 'dtype' in self.request.POST:
    #   print(self.request.POST['dtype'])
    # else :
    #   print ("No dtype?!")
    super(DiskLayout, self).save(*args, **kwargs)

class RaidLayout(DiskLayout):
  class Meta:
    verbose_name = "Software RAID Layout"
  class DiskTypes(models.TextChoices):
    SCSI = 'scsi', 'SCSI Disk'
    NVME = 'nvme', 'NVMe'
    MDRD = 'mdrd', 'Software RAID'
  partion_members = models.ManyToManyField('disklayouts.DiskPartition', blank=True)
  filesystem = models.CharField(max_length=100, blank=True)
  # disk_members = 
RaidLayout._meta.get_field('dtype').default=RaidLayout.DiskTypes.MDRD
  