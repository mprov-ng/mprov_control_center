from django.db import models
from django.dispatch import receiver
from django.db.models.signals import pre_save, pre_delete
from jobqueue.models import JobModule, Job, JobStatus
from scripts.models import Script

class OSDistro(models.Model):
  name=models.CharField(max_length=100)
  vendor=models.CharField(max_length=100)
  version=models.CharField(max_length=100)
  baserepo=models.ForeignKey(
    'OSRepo', 
    on_delete=models.CASCADE, 
    related_name='baseRepository',
    verbose_name='OS Base Repository',
  )
  osrepos=models.ManyToManyField(
    'OSRepo',
    blank=True,
    verbose_name="OS Repositories",
    related_name="+"
  )
  config_params=models.TextField(
    default="# None", 
    blank=True, 
    null=True,
    verbose_name="Configuration\nParameters",
  )
  scripts = models.ManyToManyField(Script, blank=True, )
  install_kernel_cmdline=models.CharField(max_length=4096, null=True, blank=True,help_text="Options to pass to the install kernel")
  class Meta:
    ordering=['name']
    verbose_name='OS Distrubution'
    verbose_name_plural='OS Distrubutions'

  def __str__(self):
      return self.name

  

class OSRepo(models.Model):
  name=models.CharField(max_length=100)
  repo_package_url=models.CharField(max_length=2048, verbose_name='Repo Package URL')

  osdistro=models.ManyToManyField(
    'OSDistro', 
    blank=True,
    through=OSDistro.osrepos.through,
    verbose_name='OS Distrubution'

  )

  def __str__(self):
      return self.name
  #sync=models.BooleanField()
  class Meta:
    ordering=['name']
    verbose_name='OS Repository'
    verbose_name_plural='OS Repositories'


@receiver(pre_save, sender=OSDistro)
def OSDistroUpdateJob(sender, **kwargs):
  OSImageJobType = None
  # get or create the OSIMAGE_UPDATE job module in the DB
  # TODO get the jobtype, do nothing if it's not defined.
  try:
      OSImageJobType = JobModule.objects.get(slug='os-image-update')
  except:
      OSImageJobType = None
  print(OSImageJobType)
  if OSImageJobType is not None:
      # save a new job, if one doesn't already exist.
      Job.objects.update_or_create(
        name="Update OS Images", module=OSImageJobType,
        defaults={'status': JobStatus.objects.get(pk=1)}
      )

@receiver(pre_delete, sender=OSDistro)
def OSDistroDeleteJob(sender, **kwargs):
  OSImageJobType = None
  try:
      OSImageJobType = JobModule.objects.get(slug='os-image-delete')
  except:
      OSImageJobType = None
  print(OSImageJobType)
  # get or create the OSIMAGE_UPDATE job module in the DB
  # TODO get the jobtype, do nothing if it's not defined.
  if OSImageJobType is not None:
      # save a new job, if one doesn't already exist.
      Job.objects.update_or_create(
        name="Delete OS Images", module=OSImageJobType,
        defaults={'status': JobStatus.objects.get(pk=1)}
      )
        
@receiver(pre_save, sender=OSRepo)
def RepoUpdateJob(sender, **kwargs):
  RepoJobType = None
  # get or create the OSIMAGE_UPDATE job module in the DB
  # TODO get the jobtype, do nothing if it's not defined.
  try:
      RepoJobType = JobModule.objects.get(slug='repo-update')
  except:
      RepoJobType = None
  print(RepoJobType)
  if RepoJobType is not None:
      # save a new job, if one doesn't already exist.
      Job.objects.update_or_create(
        name="Update Repos", module=RepoJobType,
        defaults={'status': JobStatus.objects.get(pk=1)}
      )

@receiver(pre_delete, sender=OSRepo)
def RepoDeleteJob(sender, **kwargs):
  RepoJobType = None
  try:
      RepoJobType = JobModule.objects.get(slug='repo-delete')
  except:
      RepoJobType = None
  print(RepoJobType)
  # get or create the OSIMAGE_UPDATE job module in the DB
  # TODO get the jobtype, do nothing if it's not defined.
  if RepoJobType is not None:
      # save a new job, if one doesn't already exist.
      Job.objects.update_or_create(
        name="Delete Repos", module=RepoJobType,
        defaults={'status': JobStatus.objects.get(pk=1)}
      )        