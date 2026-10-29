from django.db import models
from django.dispatch import receiver
from django.db.models.signals import pre_delete, post_save
from jobqueue.models import JobModule, Job, JobStatus, JobServer, queue_job
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
  ARCH = (
     ("x86_64", "x86_64"),
     ("aarch64", "aarch64"),
     ("ppc64le", "ppc64le"),
     ("s390x", "s390x"),
  )
  endpoint="/distros/"
  name=models.CharField(max_length=100)
  vendor=models.CharField(max_length=100)
  version=models.CharField(max_length=100)
  distType=models.ForeignKey(OSType, on_delete=models.SET_NULL, blank=True, null=True, verbose_name="OS Type")
  distArch=models.CharField(max_length=400,default="x86_64", choices=ARCH)
  managed=models.BooleanField(
    default=False,
    verbose_name="Mirror the generated repositories locally",
    help_text="Copied onto each repository that \"Generate OS repositories on save\" creates. A mirrored "
              "(managed) repository is downloaded and served by the job servers; each one can be several GB. "
              "Unchecked, nodes and image builds use the upstream URLs directly.",
  )
  update=models.BooleanField(
    default=False,
    verbose_name="Generate OS repositories on save",
    help_text="When saved with this checked, creates or refreshes this distribution's AppStream, BaseOS, extras, "
              "PowerTools (CRB for version 9 and later) and EPEL repositories from the Base URL, sets them as its "
              "base and OS repositories, and then clears this box. It does not update any packages.",
  )
  baseurl=models.CharField(
    max_length=4096,
    verbose_name="Base URL",
    help_text="The distribution's repository root, e.g. https://download.rockylinux.org/pub/rocky/8. "
              "Repositories are generated as <Base URL>/<repo>/<arch>/os/.",
  )
  baserepo=models.ForeignKey(
    'OSRepo', 
    on_delete=models.CASCADE, 
    related_name='baseRepository',
    verbose_name='OS Base Repository',
    blank=True,
    null=True
  )
  osrepos=models.ManyToManyField(
    'OSRepo',
    blank=True,
    verbose_name="OS Repositories",
    related_name="+"
  )
  extrarepos=models.ManyToManyField(
    'OSRepo',
    blank=True,
    verbose_name="Extra Repositories",
    related_name="+"
  )
  config_params=models.TextField(
    default="# None", 
    blank=True, 
    null=True,
    verbose_name="Configuration Parameters",
    help_text="YAML. System groups, images and systems inherit these, merged by top-level key: a key they set replaces that key's whole value here.",
  )
  scripts = models.ManyToManyField(Script, blank=True, )
  ansibleplaybooks = models.ManyToManyField(AnsiblePlaybook, blank=True, verbose_name="Ansible Playbooks" )
  ansibleroles = models.ManyToManyField(AnsibleRole, blank=True, verbose_name="Ansible Roles" )
  ansiblecollections = models.ManyToManyField(AnsibleCollection, blank=True, verbose_name="Ansible Collections" )
  
  install_kernel_cmdline=models.CharField(max_length=4096, default="",help_text="Options to pass to the install kernel. System groups and systems add to these, or replace them with a value starting with =.", blank=True)
  # install kernel parameters.
  tmpfs_root_size = models.IntegerField(default=8, help_text="Size of the root tmpfs filesystem in Gigabytes.")
  initial_mods = models.CharField(default="e1000,tg3", help_text="Comma-separated list of modules to load. System groups and systems add to these, or replace them with a value starting with =.", max_length=255)
  prov_interface = models.CharField(default="eth0", help_text="Interface name to provision over.", max_length=255)
  rootpw = models.CharField(default="changeme", help_text="Root password for the image.", max_length=255, verbose_name="Root Password", blank=True)
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
  managed = models.BooleanField(default=False, verbose_name="Mirror locally", help_text="Download this repository and serve a local copy from the job servers (repo-update/reposync). Unchecked, nodes and image builds use the Repo Package URL directly.")
  resync = models.BooleanField(default=False, verbose_name="Re-sync on save", help_text="On a mirrored repository, saving with this checked bumps the local version and queues a repo-update job to download it again, then clears this box. No effect on a repository that isn't mirrored.")
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

@receiver(post_save, sender=OSDistro)
def OSDistroCreateRepos(sender, instance, **kwargs):
  if hasattr(instance, "_post_save"):
    # if we are fired off from a previous post_save call, skip.
    return
  if not instance.update:
    # if we are not set to update, skip.
    return
  # remove trailing slashes
  baseURL=instance.baseurl.rstrip('/')

  genRepos = ['AppStream', 'BaseOS', 'extras' ]
  if float(instance.version) >= 9:
    genRepos.append('CRB')
  else: 
    genRepos.append('PowerTools')
 

  # loop through genRepos and create Repos for each one
  for repo in genRepos:
    newRepo = OSRepo.objects.filter(name=f"{repo}-{instance.version}")
    if newRepo.count() > 0:
       newRepo = newRepo[0]
    else:
      newRepo = OSRepo()
    newRepo.name = f"{repo}-{instance.version}"
    url = f"{baseURL}/{repo}/{instance.distArch}/os/"
    # only download a repo again if it's new, moved, or newly mirrored.
    newRepo.resync = newRepo.pk is None or newRepo.repo_package_url != url or (instance.managed and not newRepo.managed)
    newRepo.repo_package_url = url
    newRepo.managed = instance.managed
    newRepo.ostype = instance.distType
    newRepo.save()
    newRepo.refresh_from_db()

    if repo == "BaseOS":
      instance.baserepo = newRepo
    else:
       instance.osrepos.add(newRepo)
  newRepo = None
  # special case for EPEL
  # https://dl.fedoraproject.org/pub/archive/epel/8.8/Everything/x86_64/
  newRepo = OSRepo.objects.filter(name=f"EPEL-{instance.version}")
  if newRepo.count() > 0:
      newRepo = newRepo[0]
  else:
    newRepo = OSRepo()
  newRepo.name = f"EPEL-{instance.version}"
  # if the version has a . in it, use the archive.  If not, assume latest and pull from the main (non-archive) tree.
  if "." in instance.version:
    url = f"https://dl.fedoraproject.org/pub/archive/epel/{instance.version}/Everything/{instance.distArch}/"
  else:
    url = f"https://dl.fedoraproject.org/pub/epel/{instance.version}/Everything/{instance.distArch}/"
  newRepo.resync = newRepo.pk is None or newRepo.repo_package_url != url or (instance.managed and not newRepo.managed)
  newRepo.repo_package_url = url
  # managed follows the distro
  newRepo.managed = instance.managed
  newRepo.ostype = instance.distType
  newRepo.save()
  newRepo.refresh_from_db()
  instance.osrepos.add(newRepo)
  instance.update = False
  try: 
    instance._post_save = True
    instance.save()
  finally:
      del instance._post_save

@receiver(post_save, sender=OSRepo)
def RepoUpdateJob(sender, instance, **kwargs):
  if hasattr(instance, '_post_save'):
     # if we are fired off from a previous post_save call, skip post_save.
     return
  
  RepoJobType = None
  # get the jobtype, do nothing if it's not defined.
  try:
      RepoJobType = JobModule.objects.get(slug='repo-update')
  except JobModule.DoesNotExist:
      RepoJobType = None
  if RepoJobType is not None and instance.resync and instance.id is not None:
      # resync is one-shot: clear it in the save that queues the job, so later
      # saves (e.g. a job server adding itself to hosted_by) don't re-sync.
      instance.resync = False
      if instance.managed:
        instance.version = instance.version +1 
        # queue a repo-update job.
        queue_job(RepoJobType, { 'repo_id': instance.id})
        instance.hosted_by.clear()
      try: 
        instance._post_save = True
        instance.save()
      finally:
         del instance._post_save

@receiver(pre_delete, sender=OSRepo)
def RepoDeleteJob(sender, **kwargs):
  RepoJobType = None
  try:
      RepoJobType = JobModule.objects.get(slug='repo-delete')
  except JobModule.DoesNotExist:
      RepoJobType = None
  # get the jobtype, do nothing if it's not defined.
  if RepoJobType is not None:
      # save a new job, if one doesn't already exist.
      Job.objects.update_or_create(
        name="Delete Repos", module=RepoJobType,
        defaults={'status': JobStatus.objects.get(pk=1)}
      )        


@receiver(pre_delete, sender=JobServer)
def DeleteJobserver(sender, instance, **kwargs):
    RepoJobType = None
    # get the jobtype, do nothing if it's not defined.
    try:
        RepoJobType = JobModule.objects.get(slug='repo-update')
    except JobModule.DoesNotExist:
        RepoJobType = None
    
    if RepoJobType is not None:
        # queue a repo-update job for every repo.
        repos = OSRepo.objects.all()
        for repo in repos:
          queue_job(RepoJobType, { 'repo_id': repo.id})
    
