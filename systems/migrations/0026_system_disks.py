# Generated by Django 3.2.13 on 2022-08-05 20:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('disklayouts', '0005_alter_disklayout_system'),
        ('systems', '0025_remove_system_bootdisk'),
    ]

    operations = [
        migrations.AddField(
            model_name='system',
            name='disks',
            field=models.ManyToManyField(blank=True, related_name='disks', to='disklayouts.DiskLayout'),
        ),
    ]
