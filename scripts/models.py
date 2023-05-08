from enum import unique
from pyexpat import model
from django.db import models
from django.db.models.signals import pre_save, post_delete
from django.dispatch import receiver
from django.utils.text import slugify
from django.conf import settings
import os


class ScriptType(models.Model):
  name = models.CharField(max_length=100)
  slug = models.SlugField(unique=True, primary_key=True)

  def __str__(self):
    return self.name

class Script(models.Model):
  """
  Scripts are small snippets of code that will be run by the mProv 
  Jobserver on a system or system image.  They are usally run in the 
  system image at generation time, or on the system after it has booted,
  also known as 'post boot'
  """
  endpoint="/scripts/"
  name=models.CharField(max_length=120, verbose_name=("Script Name"))
  slug=models.SlugField(unique=True, primary_key=True)
  filename = models.FileField(upload_to='')
  scriptType = models.ForeignKey(ScriptType, on_delete=models.SET_NULL, null=True)
  version = models.BigIntegerField(default=1)
  dependsOn = models.ManyToManyField('self',blank=True,symmetrical=False)
  
  def __str__(self):
    return self.name

  def save(self, *args, **kwargs):
    if not self.slug:
      self.slug = slugify(self.filename.name)
    if not os.path.exists(settings.MEDIA_ROOT + '/' + self.scriptType.slug): 
      # make the dir
      try:
        os.makedirs(settings.MEDIA_ROOT + '/' + self.scriptType.slug, exist_ok=True)
      except: 
        print(f"Error: Unable to make script type dir: {settings.MEDIA_ROOT + '/' + self.scriptType.slug}")
        return

    self.filename.name = self.scriptType.slug + '/' + self.slug + "-v" + str(self.version)
    super(Script, self).save(*args, **kwargs)
    print(os.path.join(settings.MEDIA_ROOT, self.filename.name))
    if os.path.exists(os.path.join(settings.MEDIA_ROOT, self.filename.name)):
      print("Converting file")
      os.system("dos2unix " + os.path.join(settings.MEDIA_ROOT, self.filename.name))

class AnsiblePlaybook(models.Model):
  """
  Ansible playbooks are single file lists ansible tasks that will be run by the 'run_ansible.sh' script
  via the mProv Jobserver.
  """
  endpoint="/ansibleplaybook/"
  name=models.CharField(max_length=120, verbose_name=("Playbook Name"))
  slug=models.SlugField(unique=True, primary_key=True)
  filename = models.FileField(upload_to='')
  scriptType = models.ForeignKey(ScriptType, on_delete=models.SET_NULL, null=True, verbose_name="Playbook Type")
  version = models.BigIntegerField(default=1)
  dependsOn = models.ManyToManyField('self',blank=True,symmetrical=False)
  class Meta:
    verbose_name = "Ansible Playbook"

  def __str__(self):
    return self.name

  def save(self, *args, **kwargs):
    if not self.slug:
      self.slug = slugify(self.filename.name)
    if not os.path.exists(settings.MEDIA_ROOT + '/ansibleplaybooks/' + self.scriptType.slug): 
      # make the dir
      try:
        os.makedirs(settings.MEDIA_ROOT + '/ansibleplaybooks/' + self.scriptType.slug, exist_ok=True)
      except: 
        print(f"Error: Unalbe to make script type dir: {settings.MEDIA_ROOT + '/ansibleplaybooks/' + self.scriptType.slug}")
        return

    self.filename.name = self.scriptType.slug + '/ansibleplaybooks/' + self.slug + "-v" + str(self.version)
    super(AnsiblePlaybook, self).save(*args, **kwargs)
    print(os.path.join(settings.MEDIA_ROOT, self.filename.name))
    if os.path.exists(os.path.join(settings.MEDIA_ROOT, self.filename.name)):
      print("Converting file")
      os.system("dos2unix " + os.path.join(settings.MEDIA_ROOT, self.filename.name))

class AnsibleRole(models.Model):
  ''' 
    Ansible Roles packed groups of playbooks with configuration data all wrapped up together. 
    This section of config management is where you can add either git repositories that contain a single role,
    or ansible galaxy roles that the 'run_ansible.sh' will attempt to download run if they are associated with a 
    system, system image, system group, or OS Distribution.
  '''
  endpoint="/ansiblerole/"
  name=models.CharField(max_length=120, verbose_name="Role Name")
  slug=models.SlugField(unique=True, primary_key=True)
  roleurl = models.CharField(max_length=2048, verbose_name="Role URL", help_text="This can be a URL to a specific git repository housing a role or an Ansible Galaxy Role descriptor.  See the 'ansible-galaxy' command for help." )
  scriptType = models.ForeignKey(ScriptType, on_delete=models.SET_NULL, null=True, verbose_name="Role Type")
  version = models.BigIntegerField(default=1)
  dependsOn = models.ManyToManyField('self',blank=True,symmetrical=False)
  class Meta:
    verbose_name = "Ansible Role"

  def __str__(self):
    return self.name

  def save(self, *args, **kwargs):
    if not self.slug:
      self.slug = slugify(os.path.basename(self.roleurl))
    super(AnsibleRole, self).save(*args, **kwargs)
    # if not os.path.exists(settings.MEDIA_ROOT + '/ansibleroles/' + self.scriptType.slug): 
    #   # make the dir
    #   try:
    #     os.makedirs(settings.MEDIA_ROOT + '/ansibleroles/' + self.scriptType.slug, exist_ok=True)
    #   except: 
    #     print(f"Error: Unalbe to make script type dir: {settings.MEDIA_ROOT + '/ansibleplansibleroleaybooks/' + self.scriptType.slug}")
    #     return

    # self.filename.name = self.scriptType.slug + '/ansibleroles/' + self.slug + "-v" + str(self.version)
    # super(AnsibleRole, self).save(*args, **kwargs)
    # print(os.path.join(settings.MEDIA_ROOT, self.filename.name))
    # if os.path.exists(os.path.join(settings.MEDIA_ROOT, self.filename.name)):
    #   print("Converting file")
    #   os.system("dos2unix " + os.path.join(settings.MEDIA_ROOT, self.filename.name))


@receiver(post_delete, sender=Script)
def DeleteScript(sender, instance, **kwargs):
  # TODO: Delete scripts from the filesystem when
  # they are removed in the admin interface.
  pass