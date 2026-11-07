""" Agent credentials (#381): the client certificates the mPCC's CA has
issued to job servers and booted systems.  Each maps to a service user, so a
request authenticated with one has a real request.user for attribution. """
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
