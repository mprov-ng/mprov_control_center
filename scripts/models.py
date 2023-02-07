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
        print(f"Error: Unalbe to make script type dir: {settings.MEDIA_ROOT + '/' + self.scriptType.slug}")
        return

    self.filename.name = self.scriptType.slug + '/' + self.slug + "-v" + str(self.version)
    super(Script, self).save(*args, **kwargs)
    print(os.path.join(settings.MEDIA_ROOT, self.filename.name))
    if os.path.exists(os.path.join(settings.MEDIA_ROOT, self.filename.name)):
      print("Converting file")
      os.system("dos2unix " + os.path.join(settings.MEDIA_ROOT, self.filename.name))

  


@receiver(post_delete, sender=Script)
def DeleteScript(sender, instance, **kwargs):
  # TODO: Delete scripts from the filesystem when
  # they are removed in the admin interface.
  pass