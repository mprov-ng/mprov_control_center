# Generated by Django 3.2.23 on 2023-11-15 02:26

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('systems', '0051_networkinterface_hostaliases'),
    ]

    operations = [
        migrations.CreateModel(
            name='NADSSystem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mac', models.CharField(max_length=100, unique=True, verbose_name='MAC Address')),
                ('discovered', models.DateTimeField(auto_now_add=True, verbose_name='Discovered')),
                ('system', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='systems.system', verbose_name='Assign System')),
            ],
            options={
                'verbose_name': 'N.A.D.S Discovered',
                'verbose_name_plural': 'N.A.D.S Discovered',
            },
        ),
    ]
