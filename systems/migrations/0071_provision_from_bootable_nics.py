from django.db import migrations, models


def provision_from_bootable_nics(apps, schema_editor):
    """ Before 0070 a system netbooted when it had a bootable NIC, and the
    stateful installer cleared bootable on every NIC once it had installed.
    Carry that over to provision, and leave each system with at most one
    bootable NIC: the one named by prov_interface, otherwise the oldest. """
    System = apps.get_model('systems', 'System')
    NetworkInterface = apps.get_model('systems', 'NetworkInterface')
    for system in System.objects.all():
        nics = NetworkInterface.objects.filter(system=system, bootable=True).order_by('id')
        if not nics.exists():
            system.provision = False
            system.save(update_fields=['provision'])
            continue
        keep = nics.filter(name=system.prov_interface).first() or nics.first()
        nics.exclude(pk=keep.pk).update(bootable=False)


class Migration(migrations.Migration):

    dependencies = [
        ('systems', '0070_add_provision_field_to_system'),
    ]

    operations = [
        migrations.AlterField(
            model_name='system',
            name='provision',
            field=models.BooleanField(default=True, help_text='Should this system be provisioned (installed or netbooted) on its next PXE boot? The stateful installer clears this once it has installed.', verbose_name='Provision?'),
        ),
        migrations.RunPython(provision_from_bootable_nics, migrations.RunPython.noop),
    ]
