from enum import unique
from pyexpat import model
from django.db import models
from django.db.models.signals import pre_save, post_delete
from django.dispatch import receiver
from django.utils.text import slugify


class ScriptType(models.Model):
  name = models.CharField(max_length=100)
  slug = models.SlugField(unique=True, primary_key=True)

  def __str__(self):
    return self.name

class Script(models.Model):
  name=models.CharField(max_length=120, verbose_name=("Script Name"))
  slug=models.SlugField(unique=True, primary_key=True)
  filename = models.FileField(upload_to='')
  scriptType = models.ForeignKey(ScriptType, on_delete=models.SET_NULL, null=True)
  version = models.BigIntegerField(default=1)
  dependsOn = models.ManyToManyField('self',blank=True)

  def save(self, *args, **kwargs):
    if not self.slug:
      self.slug = slugify(self.filename.name)
    self.filename.name = self.slug + "-v" + str(self.version)
    super(Script, self).save(*args, **kwargs)


@receiver(post_delete, sender=Script)
def DeleteScript(sender, instance, **kwargs):
  # TODO: Delete scripts from the filesystem when
  # they are removed in the admin interface.
  pass