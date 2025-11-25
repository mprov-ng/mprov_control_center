# 
from django.db import migrations, models
import django.utils.timezone

def delete_old_modules(apps, schema_editor):
    JobModule = apps.get_model('jobqueue', 'JobModule')
    JobModule.objects.filter(slug__in=['os-image-update', 'os-image-delete']).delete()

class Migration(migrations.Migration):

    dependencies = [
        ('jobqueue', '0012_auto_20240123_0318'),
    ]

    operations = [
        migrations.RunPython(delete_old_modules)
    ]
