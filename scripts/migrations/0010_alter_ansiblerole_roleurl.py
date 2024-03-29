# Generated by Django 3.2.18 on 2023-04-03 20:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scripts', '0009_remove_ansiblerole_filename'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ansiblerole',
            name='roleurl',
            field=models.CharField(help_text="This can be a URL to a specific git repository housing a role or an Ansible Galaxy Role descriptor.  See the 'ansible-galaxy' command for help.", max_length=2048, verbose_name='Role URL'),
        ),
    ]
