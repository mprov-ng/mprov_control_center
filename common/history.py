""" API writes in the Admin Site History (#5).

An API create, change or delete records the same LogEntry the admin does,
as the acting user (common.request.acting_user): a person, an agent's own
service user, or mprov.shared-key for the shared API key.  The change
message is the admin's JSON form and names the changed fields, never their
values, so a BMC password change shows as "Changed Password".

Operational churn isn't recorded: the job queue (jobs, job servers and
their addresses and modules) and the agents' credentials (pki), which job
servers and nodes write constantly and pki logs itself. """
import logging

from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.utils.text import capfirst

log = logging.getLogger("mprov.history")

NOT_RECORDED_APPS = {"jobqueue", "pki"}

__all__ = ["ADDITION", "CHANGE", "DELETION", "record", "recorded", "snapshot", "changed_fields"]


def recorded(model):
    """ Whether changes to model go in the History. """
    return model._meta.app_label not in NOT_RECORDED_APPS


def snapshot(instance, names):
    """ {name: value} for the model fields among names: the stored value, or
    the set of related pks for a many-to-many.  Other names are left out. """
    values = {}
    for name in names:
        try:
            field = instance._meta.get_field(name)
        except Exception:
            continue
        if field.many_to_many:
            values[name] = set(getattr(instance, name).values_list("pk", flat=True)) if instance.pk else set()
        elif field.concrete:
            values[name] = getattr(instance, field.attname)
    return values


def changed_fields(before, after):
    return [name for name in before if before[name] != after.get(name)]


def _label(model, name):
    try:
        return capfirst(str(model._meta.get_field(name).verbose_name))
    except Exception:
        return capfirst(name)


def record(request, instance, action, fields=()):
    """ Record one API create (ADDITION), change (CHANGE, with the names of the
    fields that changed) or delete (DELETION, before it's deleted).  A change
    that changed nothing isn't recorded. """
    from common.request import acting_user
    model = type(instance)
    if not recorded(model) or request is None:
        return
    if action == CHANGE and not fields:
        return
    user = acting_user(request)
    if user is None:
        return
    if action == ADDITION:
        message = [{"added": {}}]
    elif action == CHANGE:
        message = [{"changed": {"fields": [_label(model, name) for name in fields]}}]
    else:
        message = [{"deleted": {}}]
    try:
        LogEntry.objects.log_actions(user_id=user.pk, queryset=[instance], action_flag=action,
                                     change_message=message, single_object=True)
    except Exception as e:
        # history is a record, never a reason for the write itself to fail
        log.error(f"couldn't record {model._meta.label} {instance.pk} in the history: {e}")
