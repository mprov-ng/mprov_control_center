# Generated by Django 3.2.22 on 2025-01-09 16:57

from django.db import migrations, models

def updateVlan(apps, schema_editor):
    Network = apps.get_model('networks', 'Network')
    Network.objects.filter(vlan='default').update(vlan=1)


class Migration(migrations.Migration):

    dependencies = [
        ('networks', '0016_auto_20240123_0318'),
    ]

    operations = [
        migrations.AlterField(
            model_name='network',
            name='vlan',
            field=models.CharField(default='1', max_length=100),
        ),
        migrations.RunPython(updateVlan),
        
    ]
