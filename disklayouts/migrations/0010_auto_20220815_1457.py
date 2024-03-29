# Generated by Django 3.2.13 on 2022-08-15 14:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('disklayouts', '0009_rename_type_disklayout_dtype'),
    ]

    operations = [
        migrations.AlterField(
            model_name='disklayout',
            name='dtype',
            field=models.CharField(choices=[('scsi', 'SCSI Disk'), ('nvme', 'NVMe'), ('mdrd', 'Sofware RAID')], default='scsi', max_length=4, verbose_name='Disk Type'),
        ),
        migrations.AlterField(
            model_name='disklayout',
            name='slug',
            field=models.SlugField(blank=True, primary_key=True, serialize=False, unique=True),
        ),
    ]
