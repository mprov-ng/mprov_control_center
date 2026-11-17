from django.db import migrations, models
from django.db.models import Count
from django.db.models.functions import Lower


def check_unique_names(apps, schema_editor):
    """ A system's NIC names become unique (#581).  Stop, before anything is
    changed, if a system has two NICs with the same name (ignoring case, as
    MariaDB does), naming them, so they can be renamed or deleted first. """
    NetworkInterface = apps.get_model('systems', 'NetworkInterface')
    nics = NetworkInterface.objects.annotate(lname=Lower('name'))
    dupes = (nics.values('system_id', 'lname').annotate(n=Count('id')).filter(n__gt=1)
             .order_by('system_id', 'lname').values_list('system_id', 'lname'))
    if dupes:
        lines = []
        for system_id, name in dupes:
            group = nics.filter(system_id=system_id, lname=name).select_related('system').order_by('id')
            names = ', '.join(f"{nic.name} (id {nic.id})" for nic in group)
            lines.append(f"  {group[0].system.hostname} (system id {system_id}): {names}")
        raise RuntimeError(
            "Network interface names must now be unique on each system, but these are used more than once:\n" +
            "\n".join(lines) +
            "\nRename or delete the extra interfaces (on the system's page in the admin, on the previous version) "
            "and run the upgrade again.")


class Migration(migrations.Migration):

    dependencies = [
        ('systems', '0080_networkinterface_guid'),
    ]

    operations = [
        # first, so nothing is changed if it fails (MariaDB doesn't roll back DDL)
        migrations.RunPython(check_unique_names, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='networkinterface',
            constraint=models.UniqueConstraint(fields=('system', 'name'), name='networkinterface_unique_system_name',
                                               violation_error_message='This system already has an interface with this name.'),
        ),
    ]
