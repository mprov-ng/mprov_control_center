from django.db import migrations


def clear_stale_needs_rebuild(apps, schema_editor):
  """ The "Rebuild selected images now" action queued its image-update job
  but left needs_rebuild set (#556).  While it's set, job servers don't
  register as hosts of the image, and the image's next save queues another
  build.  With an image-update job module, every other way of asking for a
  rebuild queues the job and clears the flag in the same save, so a set flag
  is always one of these: the build it asked for was already queued.  Without
  the module, a set flag is a rebuild still waiting to be queued: keep it. """
  JobModule = apps.get_model('jobqueue', 'JobModule')
  SystemImage = apps.get_model('systems', 'SystemImage')
  if JobModule.objects.filter(slug='image-update').exists():
    SystemImage.objects.filter(needs_rebuild=True).update(needs_rebuild=False)


class Migration(migrations.Migration):

  dependencies = [
    ('jobqueue', '0021_jobserveraddress_address_255'),
    ('systems', '0078_managed_files'),
  ]

  operations = [
    migrations.RunPython(clear_stale_needs_rebuild, migrations.RunPython.noop),
  ]
