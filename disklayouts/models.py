from django.db import models


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
  mount=models.CharField(verbose_name="Mount Point", max_length=4096)
  size=models.BigIntegerField(verbose_name="Size")
  fill=models.BooleanField(default=False, verbose_name="Grow to fill?")
  filesystem=models.CharField(verbose_name="Filesysetm", max_length=255)
  disklayout = models.ForeignKey("DiskLayout", verbose_name="Associated Layout")
  pass

class DiskLayout(models.Model):
  name = models.CharField(verbose_name="Layout Name", max_length=255)
  diskname = models.CharField(verbose_name="Disk Device", max_length=255)


  pass