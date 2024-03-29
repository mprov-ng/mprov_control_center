# Generated by Django 3.2.18 on 2023-05-18 14:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scripts', '0011_ansiblecollection'),
        ('systems', '0047_rename_ansibleroless_system_ansibleroles'),
    ]

    operations = [
        migrations.AddField(
            model_name='system',
            name='ansiblecollections',
            field=models.ManyToManyField(blank=True, to='scripts.AnsibleCollection', verbose_name='Ansible Collections'),
        ),
        migrations.AddField(
            model_name='systemgroup',
            name='ansiblecollections',
            field=models.ManyToManyField(blank=True, to='scripts.AnsibleCollection', verbose_name='Ansible Collections'),
        ),
        migrations.AddField(
            model_name='systemimage',
            name='ansiblecollections',
            field=models.ManyToManyField(blank=True, to='scripts.AnsibleCollection', verbose_name='Ansible Collections'),
        ),
    ]
