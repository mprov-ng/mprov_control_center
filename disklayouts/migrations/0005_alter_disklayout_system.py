# Generated by Django 3.2.13 on 2022-08-05 20:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('systems', '0025_remove_system_bootdisk'),
        ('disklayouts', '0004_disklayout_system'),
    ]

    operations = [
        migrations.AlterField(
            model_name='disklayout',
            name='system',
            field=models.ManyToManyField(blank=True, related_name='systems', to='systems.System'),
        ),
    ]
