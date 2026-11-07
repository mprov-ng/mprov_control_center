# Serial number tracking with history (#60).

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('systems', '0073_system_last_booted'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='system',
            name='serial',
            field=models.CharField(blank=True, help_text='Reported by the node at boot, or by N.A.D.S.; set it here to correct it.  Each change is kept in the serial history.', max_length=255, null=True, verbose_name='Serial Number'),
        ),
        migrations.CreateModel(
            name='SystemSerialHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('old_serial', models.CharField(blank=True, max_length=255, null=True, verbose_name='Old Serial Number')),
                ('new_serial', models.CharField(blank=True, max_length=255, null=True, verbose_name='New Serial Number')),
                ('changed', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Changed')),
                ('source', models.CharField(choices=[('admin', 'Admin'), ('api', 'API'), ('nads', 'N.A.D.S.'), ('node', 'Node at boot')], max_length=16, verbose_name='Changed By')),
                ('changed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='User')),
                ('system', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='serial_history', to='systems.system')),
            ],
            options={
                'verbose_name': 'Serial Number Change',
                'verbose_name_plural': 'Serial Number History',
                'ordering': ['-changed', '-id'],
            },
        ),
    ]
