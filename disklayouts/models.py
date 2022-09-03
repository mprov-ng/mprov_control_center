from curses.ascii import FF
from email.policy import default
from urllib import request
from django.db import models
from django.utils.text import slugify
from django.core.validators import MinValueValidator



class DiskPartition(models.Model):
  partnum = models.PositiveIntegerField(verbose_name="Part. Number", validators=[MinValueValidator(1)],default=1)
  mount=models.CharField(verbose_name="Mount Point", max_length=4096, help_text="The directory this partition will mount to or 'raid' if it is a Software RAID member.")
  size=models.BigIntegerField(verbose_name="Size (in MB)")
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
  class RaidLevels(models.TextChoices):
    RAID0 = 'raid0', 'RAID 0'
    RAID1 = 'raid1', 'RAID 1'
    RAID5 = 'raid5', 'RAID 5'
    RAID6 = 'raid6', 'RAID 6'

  partition_members = models.ManyToManyField('disklayouts.DiskPartition', blank=True)
  filesystem = models.CharField(max_length=100, blank=True)
  raidlevel = models.CharField(max_length=6, choices=RaidLevels.choices, verbose_name="RAID Level", default=RaidLevels.RAID0)
  mount = models.CharField(max_length=4096, verbose_name="Mount Point")
  
RaidLayout._meta.get_field('dtype').default=RaidLayout.DiskTypes.MDRD
  