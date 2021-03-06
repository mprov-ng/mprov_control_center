# Generated by Django 3.2.12 on 2022-04-29 18:44

from django.db import migrations, models
from django.utils.text import slugify

def add_slug(apps, schema_editor):
    Network = apps.get_model('networks', 'Network')
    for net in Network.objects.all():
        net.slug = slugify(net.name)
        net.save()

def remove_slug(apps, schema_editor):
    Network = apps.get_model('networks', 'Network')
    for net in Network.objects.all():
        net.slug = None
        net.save()

class Migration(migrations.Migration):

    dependencies = [
        ('networks', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='network',
            name='slug',
            field=models.SlugField(blank=True),
        ),
        migrations.RunPython(add_slug, remove_slug)
    ]
