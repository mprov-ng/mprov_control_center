""" Agent credentials (#381): the client certificates the mPCC's CA has
issued to job servers and booted systems.  Each maps to a service user, so a
request authenticated with one has a real request.user for attribution. """
import datetime
import hashlib
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.utils import timezone


class AgentCredentialQuerySet(models.QuerySet):
    def active(self, now=None):
        """ The credentials that aren't revoked and are in date. """
        now = now or timezone.now()
        return self.filter(revoked_at__isnull=True, not_before__lte=now, not_after__gt=now)


class AgentCredential(models.Model):
    """ A client certificate the mPCC issued to one job server or one system.
    Revoking it here takes effect on the agent's next request. """
    JOBSERVER = "jobserver"
    SYSTEM = "system"
    KINDS = [(JOBSERVER, "Job server"), (SYSTEM, "System")]

    kind = models.CharField(max_length=16, choices=KINDS)
    # deleting the job server or system deletes its credentials, which
    # revokes them: a certificate with no row here is refused.
    jobserver = models.ForeignKey('jobqueue.JobServer', null=True, blank=True, on_delete=models.CASCADE,
                                  related_name='credentials', verbose_name="Job Server")
    system = models.ForeignKey('systems.System', null=True, blank=True, on_delete=models.CASCADE,
                               related_name='credentials')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='agent_credentials',
                             verbose_name="Service User")
    serial = models.CharField(max_length=40, unique=True, help_text="The certificate's serial number, in hex.")
    fingerprint = models.CharField(max_length=64, unique=True, verbose_name="SHA-256 Fingerprint")
    certificate = models.TextField(help_text="The certificate, in PEM.")
    not_before = models.DateTimeField(verbose_name="Valid From")
    not_after = models.DateTimeField(verbose_name="Valid To")
    created = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True, verbose_name="Revoked")
    last_seen = models.DateTimeField(null=True, blank=True, verbose_name="Last Seen")

    objects = AgentCredentialQuerySet.as_manager()

    class Meta:
        verbose_name = "Agent Credential"
        ordering = ['-created']
        constraints = [
            models.CheckConstraint(
                name="pki_agentcredential_one_agent",
                condition=(
                    models.Q(kind="jobserver", jobserver__isnull=False, system__isnull=True)
                    | models.Q(kind="system", system__isnull=False, jobserver__isnull=True)
                ),
            ),
        ]

    def __str__(self):
        return f"{self.user.username} ({self.serial[:12]})"

    @property
    def agent(self):
        return self.jobserver if self.kind == self.JOBSERVER else self.system

    def is_active(self, now=None):
        now = now or timezone.now()
        return self.revoked_at is None and self.not_before <= now < self.not_after
    is_active.boolean = True
    is_active.short_description = "Active"

    def revoke(self, now=None):
        if self.revoked_at is None:
            self.revoked_at = now or timezone.now()
            self.save(update_fields=["revoked_at"])


def service_username(jobserver=None, system=None):
    """ The service user's name for a job server (by its host ID) or a system (by its pk). """
    if (jobserver is None) == (system is None):
        raise ValueError("give exactly one of jobserver and system")
    if jobserver is not None:
        return f"mprov.js.{jobserver.host_id or f'pk{jobserver.pk}'}"
    return f"mprov.sys.{system.pk}"


@transaction.atomic
def service_user(jobserver=None, system=None):
    """ The service user a job server's or system's credentials act as,
    made the first time: no usable password, never staff. """
    User = get_user_model()
    name = service_username(jobserver, system)
    user, created = User.objects.get_or_create(username=name, defaults={
        "first_name": str(jobserver if jobserver is not None else system)[:150],
        "is_staff": False,
        "is_superuser": False,
    })
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])
    return user


def _hash(secret):
    return hashlib.sha256(secret.encode()).hexdigest()


class EnrollmentToken(models.Model):
    """ A one-time token a job server enrolls with (#381): single-use,
    short-lived, stored hashed and shown once when it's made. """
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    prefix = models.CharField(max_length=8, editable=False, help_text="The token's first characters, to tell tokens apart.")
    note = models.CharField(max_length=255, blank=True, help_text="Which job server it's for.")
    created = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='+', editable=False)
    expires = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True, editable=False, verbose_name="Used")
    jobserver = models.ForeignKey('jobqueue.JobServer', null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name='+', editable=False, verbose_name="Enrolled Job Server")

    class Meta:
        verbose_name = "Job Server Enrollment Token"
        ordering = ['-created']

    def __str__(self):
        return f"{self.prefix}… ({self.note or 'no note'})"

    @classmethod
    def make(cls, lifetime=datetime.timedelta(hours=24), note="", user=None):
        """ A new token: (row, the token itself, which is never stored). """
        secret = secrets.token_urlsafe(32)
        row = cls.objects.create(token_hash=_hash(secret), prefix=secret[:8], note=note, created_by=user,
                                 expires=timezone.now() + lifetime)
        return row, secret

    def usable(self, now=None):
        return self.used_at is None and (now or timezone.now()) < self.expires
    usable.boolean = True

    @classmethod
    def redeem(cls, secret):
        """ Burn a usable token and return it, or None. """
        if not isinstance(secret, str) or not secret:
            return None
        with transaction.atomic():
            row = cls.objects.select_for_update().filter(token_hash=_hash(secret)).first()
            if row is None or not row.usable():
                return None
            row.used_at = timezone.now()
            row.save(update_fields=["used_at"])
            return row


class BootNonce(models.Model):
    """ A one-time enrollment nonce for one boot of one system (#381), put on
    the kernel command line by /ipxe/ (mprov_enroll=...).  Single-use, bound
    to the address that booted, valid NONCE_LIFETIME, stored hashed. """
    NONCE_LIFETIME = datetime.timedelta(minutes=15)

    nonce_hash = models.CharField(max_length=64, unique=True)
    system = models.ForeignKey('systems.System', on_delete=models.CASCADE, related_name='+')
    ipaddress = models.GenericIPAddressField()
    created = models.DateTimeField(auto_now_add=True)
    expires = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Boot Enrollment Nonce"

    @classmethod
    def issue(cls, system, ipaddress):
        """ A new nonce for this boot; the system's unused ones are dropped. """
        cls.objects.filter(system=system, used_at__isnull=True).delete()
        nonce = secrets.token_hex(16)
        cls.objects.create(nonce_hash=_hash(nonce), system=system, ipaddress=ipaddress,
                           expires=timezone.now() + cls.NONCE_LIFETIME)
        return nonce

    @classmethod
    def redeem(cls, nonce, ipaddress):
        """ (system, None) for a usable nonce from its address, which burns it,
        or (None, reason). """
        if not isinstance(nonce, str) or not nonce:
            return None, "no nonce"
        with transaction.atomic():
            row = cls.objects.select_for_update().select_related("system").filter(nonce_hash=_hash(nonce)).first()
            if row is None:
                return None, "unknown nonce"
            if row.used_at is not None:
                return None, f"nonce already used for {row.system.hostname}"
            if timezone.now() >= row.expires:
                return None, f"nonce for {row.system.hostname} expired"
            if row.ipaddress != ipaddress:
                return None, f"nonce for {row.system.hostname} sent from {ipaddress}, not {row.ipaddress}"
            row.used_at = timezone.now()
            row.save(update_fields=["used_at"])
            return row.system, None
