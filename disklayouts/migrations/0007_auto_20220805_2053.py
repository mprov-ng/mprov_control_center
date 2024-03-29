# Generated by Django 3.2.13 on 2022-08-05 20:53

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('systems', '0027_alter_system_disks'),
        ('disklayouts', '0006_auto_20220805_2040'),
    ]

    operations = [
        migrations.AlterField(
            model_name='disklayout',
            name='systems',
            field=models.ManyToManyField(blank=True, related_name='disklayouts', to='systems.System'),
        ),
        migrations.AlterField(
            model_name='diskpartition',
            name='disklayout',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='partitions', to='disklayouts.disklayout', verbose_name='Associated Layout'),
        ),
    ]
