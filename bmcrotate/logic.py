""" Changing, checking and recovering BMC credentials through job servers (#486).

The rule everything here follows: the mPCC stores only a credential pair a
job server has just logged in to the BMC with, never one it merely tried. """
import logging

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from bmcrotate.models import BMCRotation

log = logging.getLogger("mprov.bmc")

MODULE = "bmc-rotate"
PENDING, RUNNING, FAILED, SUCCESS = 1, 2, 3, 4
RESULT_STATUSES = {BMCRotation.SUCCEEDED, BMCRotation.PARTIAL, BMCRotation.FAILED, BMCRotation.UNREACHABLE,
                   BMCRotation.UNCONFIRMED}


def available():
    """ Whether a registered job server runs bmc-rotate.  Its JobModule is
    made when such a job server registers (#256), so it exists then. """
    from jobqueue.models import JobServer
    return JobServer.objects.filter(jobmodules__slug=MODULE).exists()


def _queue(rotation):
    from jobqueue.models import Job, JobModule
    bmc = rotation.bmc
    job = Job.objects.create(name=f"BMC {rotation.kind}: {bmc.system.hostname}",
                             module=JobModule.objects.get(slug=MODULE), status_id=PENDING,
                             params={"rotation": rotation.pk, "network": bmc.network_id, "bmc": bmc.ipaddress})
    rotation.job = job
    rotation.save(update_fields=["job"])
    return job


def start(systems, kind, user, new_username="", new_password=""):
    """ Queue a change or check for every BMC of these systems.  Returns
    (rotations, systems skipped with no BMC, BMCs skipped with a request
    still open). """
    from systems.models import SystemBMC
    rotations, busy = [], []
    bmcs = SystemBMC.objects.filter(system__in=systems).select_related("system").order_by("system__hostname", "pk")
    with_bmc = {bmc.system_id for bmc in bmcs}
    skipped = sorted((s for s in systems if s.pk not in with_bmc), key=lambda s: s.hostname)
    with transaction.atomic():
        for bmc in bmcs:
            if bmc.rotations.filter(status__in=BMCRotation.OPEN).exists():
                busy.append(bmc)
                continue
            rotation = BMCRotation.objects.create(
                bmc=bmc, kind=kind, requested_by=user,
                current_username=bmc.username or "", current_password=bmc.password or "",
                new_username=(new_username or bmc.username or "") if kind == BMCRotation.CHANGE else "",
                # a blank new password keeps the current one
                new_password=(new_password or bmc.password or "") if kind == BMCRotation.CHANGE else "")
            _queue(rotation)
            rotations.append(rotation)
    names = ", ".join(r.bmc.system.hostname for r in rotations[:10]) + (" …" if len(rotations) > 10 else "")
    log.info(f"bmc: {user} queued {kind} for {len(rotations)} BMCs ({names or 'none'}); "
             f"user {'changing' if kind == BMCRotation.CHANGE and new_username else 'kept'}")
    return rotations, skipped, busy


def find(rotation, user):
    """ Queue "find which credentials work" for an unconfirmed change. """
    with transaction.atomic():
        rotation = BMCRotation.objects.select_for_update().get(pk=rotation.pk)
        if rotation.status != BMCRotation.UNCONFIRMED or not rotation.candidates:
            return False
        rotation.kind, rotation.status, rotation.error, rotation.finished = BMCRotation.FIND, BMCRotation.PENDING, "", None
        rotation.requested_by = user
        rotation.save()
        _queue(rotation)
    log.info(f"bmc: {user} queued find for {rotation.bmc.system.hostname}'s BMC")
    return True


def candidates_for(rotation):
    """ The pairs that might log in after an unconfirmed change, most likely
    last-safe first: the old pair, the new password, the new pair. """
    pairs = [{"username": rotation.current_username, "password": rotation.current_password},
             {"username": rotation.current_username, "password": rotation.new_password},
             {"username": rotation.new_username, "password": rotation.new_password}]
    unique = []
    for pair in pairs:
        if pair not in unique:
            unique.append(pair)
    return unique


def secret(rotation):
    """ What the job server running this request needs, credentials included. """
    reply = {"id": rotation.pk, "kind": rotation.kind,
             "bmc": {"ipaddress": rotation.bmc.ipaddress, "network": rotation.bmc.network_id},
             "current": {"username": rotation.current_username, "password": rotation.current_password},
             "new": None, "candidates": []}
    if rotation.kind == BMCRotation.CHANGE:
        reply["new"] = {"username": rotation.new_username, "password": rotation.new_password}
    elif rotation.kind == BMCRotation.FIND:
        reply["candidates"] = rotation.candidates
    return reply


def _store(rotation, username, password, what):
    """ Store a pair that was just verified on the BMC. """
    from systems.models import SystemBMC
    SystemBMC.objects.filter(pk=rotation.bmc_id).update(username=username, password=password,
                                                        credentials_changed=timezone.now())
    rotation.stored = what
    if rotation.requested_by_id:
        LogEntry.objects.log_actions(
            user_id=rotation.requested_by_id, queryset=[rotation.bmc], action_flag=CHANGE,
            change_message=[{"changed": {"fields": ["BMC User", "BMC Password"] if "user" in what
                                         else ["BMC Password"]}}], single_object=True)


def apply_result(rotation, data):
    """ Record a job server's result: store exactly the pair it verified.
    Returns what was stored ("" for nothing). """
    status = data.get("status")
    verified = data.get("verified")
    rotation.method = (data.get("method") or "")[:10]
    tls = data.get("tls_verified")
    rotation.tls_verified = tls if isinstance(tls, bool) else None
    rotation.error = str(data.get("error") or "")[:500]
    for secret_value in (rotation.current_password, rotation.new_password,
                         *[c.get("password", "") for c in rotation.candidates]):
        if secret_value:
            rotation.error = rotation.error.replace(secret_value, "***")
    keep = False
    if rotation.kind == BMCRotation.CHANGE:
        if verified == "new":
            _store(rotation, rotation.new_username, rotation.new_password,
                   "new user and password" if rotation.new_username != rotation.current_username else "new password")
            status = BMCRotation.SUCCEEDED if status != BMCRotation.PARTIAL else status
        elif verified == "password_only":
            _store(rotation, rotation.current_username, rotation.new_password, "new password, old user")
            status = BMCRotation.PARTIAL
        elif verified == "current":
            rotation.stored = "unchanged"
            status = status if status in (BMCRotation.FAILED, BMCRotation.UNREACHABLE) else BMCRotation.FAILED
        elif status in (BMCRotation.FAILED, BMCRotation.UNREACHABLE):
            # nothing verified, and the job server says it never got to change
            # the BMC (the current credentials were refused, or it couldn't
            # be reached): nothing changed, so nothing to find either
            rotation.stored = "unchanged"
        else:
            # it may have changed the BMC but couldn't verify a pair after:
            # keep every pair that might work
            rotation.candidates = candidates_for(rotation)
            rotation.stored = "unchanged, unconfirmed"
            status, keep = BMCRotation.UNCONFIRMED, True
    elif rotation.kind == BMCRotation.CHECK:
        rotation.stored = "unchanged"
        if verified == "current":
            status = BMCRotation.SUCCEEDED
        elif status not in (BMCRotation.UNREACHABLE,):
            status = BMCRotation.FAILED
    else:  # FIND
        index = int(verified) if isinstance(verified, str) and verified.isdigit() else None
        if index is not None and index < len(rotation.candidates):
            pair = rotation.candidates[index]
            _store(rotation, pair["username"], pair["password"], f"the credentials that worked (#{index + 1})")
            status = BMCRotation.SUCCEEDED
        else:
            # none worked: stay unconfirmed, so it can be tried again
            rotation.stored = "unchanged, none of the candidates worked"
            status, keep = BMCRotation.UNCONFIRMED, True
    rotation.status = status if status in RESULT_STATUSES else BMCRotation.FAILED
    rotation.finished = timezone.now()
    # an unconfirmed change keeps only the pairs to try
    rotation.clear_secrets(keep_candidates=keep)
    rotation.save()
    log.info(f"bmc: {rotation.kind} on {rotation.bmc.system.hostname}'s BMC: {rotation.status}, "
             f"stored {rotation.stored or 'nothing'}{'' if rotation.tls_verified is not False else ' (TLS not verified)'}")
    return rotation.stored


def job_ended(job):
    """ A bmc-rotate job finished: one that didn't report a result is
    unconfirmed (a change) or failed (a check or find). """
    rotation_id = (job.params or {}).get("rotation") if isinstance(job.params, dict) else None
    if rotation_id is None:
        return
    with transaction.atomic():
        rotation = BMCRotation.objects.select_for_update().filter(pk=rotation_id, job=job).first()
        if rotation is None or rotation.status not in (BMCRotation.PENDING, BMCRotation.RUNNING):
            return
        if rotation.kind == BMCRotation.CHANGE:
            rotation.candidates = candidates_for(rotation)
            rotation.status, rotation.stored = BMCRotation.UNCONFIRMED, "unchanged, unconfirmed"
            rotation.error = "The job ended without reporting a result; the BMC may have the new credentials."
            rotation.clear_secrets(keep_candidates=True)
        elif rotation.kind == BMCRotation.FIND:
            rotation.status, rotation.stored = BMCRotation.UNCONFIRMED, "unchanged"
            rotation.error = "The job ended without reporting a result."
        else:
            rotation.status, rotation.stored = BMCRotation.FAILED, "unchanged"
            rotation.error = "The job ended without reporting a result."
            rotation.clear_secrets()
        rotation.finished = timezone.now()
        rotation.save()
    log.warning(f"bmc: {rotation.kind} on {rotation.bmc.system.hostname}'s BMC ended without a result: {rotation.status}")
