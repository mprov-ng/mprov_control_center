# Generated by Django 3.2.18 on 2023-04-03 20:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scripts', '0010_alter_ansiblerole_roleurl'),
        ('osmanagement', '0019_alter_osdistro_ansibleplaybooks'),
    ]

    operations = [
        migrations.AddField(
            model_name='osdistro',
            name='ansibleroles',
            field=models.ManyToManyField(blank=True, to='scripts.AnsibleRole', verbose_name='Ansible Roles'),
        ),
    ]
