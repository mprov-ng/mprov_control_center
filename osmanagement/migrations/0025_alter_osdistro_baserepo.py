# Generated by Django 3.2.23 on 2024-01-21 13:44

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('osmanagement', '0024_auto_20240118_2027'),
    ]

    operations = [
        migrations.AlterField(
            model_name='osdistro',
            name='baserepo',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='baseRepository', to='osmanagement.osrepo', verbose_name='OS Base Repository'),
        ),
    ]
