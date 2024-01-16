from django.db import models
from django.dispatch import receiver
from django.db.models.signals import pre_save, pre_delete, post_save
from jobqueue.models import JobModule, Job, JobStatus, JobServer
from scripts.models import Script, AnsiblePlaybook, AnsibleRole, AnsibleCollection

# This will be an object managed by the jobserver image-update and repo-update modules.
class OSType(models.Model):
  endpoint="/ostypes/"
  slug = models.SlugField(primary_key=True)
  name = models.CharField(max_length=255)

  def __str__(self):
      return self.name

 
class OSDistro(models.Model):
  """ This is where you would define what OS Distributions you would like the mPCC to manage."""
  endpoint="/distros/"
  name=models.CharField(max_length=100)
  vendor=models.CharField(max_length=100)
  version=models.CharField(max_length=100)
  managed=models.BooleanField(default=False)
  update=models.BooleanField(default=False)
  baseurl=models.CharField(max_length=4096)
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
  ansibleplaybooks = models.ManyToManyField(AnsiblePlaybook, blank=True, verbose_name="Ansible Playbooks" )
  ansibleroles = models.ManyToManyField(AnsibleRole, blank=True, verbose_name="Ansible Roles" )
  ansiblecollections = models.ManyToManyField(AnsibleCollection, blank=True, verbose_name="Ansible Collections" )
  
  install_kernel_cmdline=models.CharField(max_length=4096, default="",help_text="Options to pass to the install kernel", blank=True)
  # install kernel parameters.
  tmpfs_root_size = models.IntegerField(default=8, help_text="Size of the root tmpfs filesystem in Gibabytes")
  initial_mods = models.CharField(default="e1000,tg3", help_text="Comma separated list of modules to load.", max_length=255)
  prov_interface = models.CharField(default="eth0", help_text="Interface name to provision over.", max_length=255)
  rootpw = models.CharField(default="changeme", help_text="Root Password for the image", max_length=255, verbose_name="Root Password", blank=True)
  rootsshkeys=models.TextField(verbose_name="Root SSH Keys", help_text="Keys to add to the authorized keys file.", blank=True)
  class Meta:
    ordering=['name']
    verbose_name='OS Distribution'
    verbose_name_plural='OS Distributions'

  def __str__(self):
      return self.name

  

class OSRepo(models.Model):
  """ This is where you would define the OS Repositories that you would like to use in OS Distribution management."""
  endpoint="/repos/"
  name=models.CharField(max_length=100)
  repo_package_url=models.CharField(max_length=2048, verbose_name='Repo Package URL')
  managed = models.BooleanField(default=False, verbose_name="mProv Managed?", help_text="Should mProv download and manage this repository?")
  update = models.BooleanField(default=False, verbose_name="Update Repository?", help_text="Should we update a managed repository?")
  hosted_by = models.ManyToManyField('jobqueue.JobServer', blank=True, verbose_name="Hosted by")
  ostype = models.ForeignKey(OSType, on_delete=models.SET_NULL, blank=True, null=True, verbose_name="OS Type")
  version = models.BigIntegerField(default=1, verbose_name="Repository Local Version", help_text="Local version of the repository, if mProv Managed.")

  # osdistro=models.ManyToManyField(
  #   'OSDistro', 
  #   blank=True,
  #   through=OSDistro.osrepos.through,
  #   verbose_name='OS Distribution'

  # )

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
        
@receiver(post_save, sender=OSRepo)
def RepoUpdateJob(sender, instance, **kwargs):
  RepoJobType = None
  # get or create the OSIMAGE_UPDATE job module in the DB
  # TODO get the jobtype, do nothing if it's not defined.
  try:
      RepoJobType = JobModule.objects.get(slug='repo-update')
  except:
      RepoJobType = None
  print(RepoJobType)
  if RepoJobType is not None and instance.update and instance.id is not None:
      instance.version = instance.version +1 
      # save a new job, if one doesn't already exist.
      params = { 'repo_id': instance.id}

      Job.objects.create( name=RepoJobType.name, 
          module=RepoJobType, 
          status=JobStatus.objects.get(pk=1), 
          params=params,          
      )
      instance.hosted_by.clear()
      instance.save()

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


@receiver(pre_delete, sender=JobServer)
def DeleteJobserver(sender, instance, **kwargs):
    RepoJobType = None
    # get or create the OSIMAGE_UPDATE job module in the DB
    # TODO get the jobtype, do nothing if it's not defined.
    try:
        RepoJobType = JobModule.objects.get(slug='repo-update')
    except:
        RepoJobType = None
    
    if RepoJobType is not None:
        # save a new job, if one doesn't already exist.
        repos = OSRepo.objects.all()
        for repo in repos:
          params = { 'repo_id': repo.id}
          Job.objects.create( name=RepoJobType.name, 
              module=RepoJobType, 
              status=JobStatus.objects.get(pk=1), 
              params=params,          
          )
    