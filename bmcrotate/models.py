""" A change (or check) of one BMC's credentials, made on the BMC by a job
server's bmc-rotate job (#486). """
from django.conf import settings
from django.db import models


class BMCRotation(models.Model):
    """ One request to change, check or recover the credentials of one BMC.

    The mPCC stores only a credential pair a job server has just logged in to
    the BMC with.  The passwords held here (the pair at the time of the
    request, the new pair, the candidates to try) are cleared once the
    request is finished; an unconfirmed one keeps its candidates until "Find
    which credentials work" settles it. """
    CHANGE, CHECK, FIND = "change", "check", "find"
    KINDS = [(CHANGE, "Change on the BMC"), (CHECK, "Check stored credentials"), (FIND, "Find which credentials work")]
    PENDING, RUNNING, SUCCEEDED, PARTIAL, FAILED, UNREACHABLE, UNCONFIRMED = (
        "pending", "running", "succeeded", "partial", "failed", "unreachable", "unconfirmed")
    STATUSES = [(PENDING, "Pending"), (RUNNING, "Running"), (SUCCEEDED, "Succeeded"),
                (PARTIAL, "Password changed, user not"), (FAILED, "Failed"), (UNREACHABLE, "Unreachable"),
                (UNCONFIRMED, "Unconfirmed")]
    OPEN = (PENDING, RUNNING, UNCONFIRMED)

    bmc = models.ForeignKey('systems.SystemBMC', on_delete=models.CASCADE, related_name='rotations')
    kind = models.CharField(max_length=10, choices=KINDS)
    status = models.CharField(max_length=12, choices=STATUSES, default=PENDING)
    job = models.ForeignKey('jobqueue.Job', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    # the credentials, cleared when the request is finished
    current_username = models.CharField(max_length=255, blank=True, default="")
    current_password = models.CharField(max_length=100, blank=True, default="")
    new_username = models.CharField(max_length=255, blank=True, default="")
    new_password = models.CharField(max_length=100, blank=True, default="")
    candidates = models.JSONField(default=list, blank=True)
    # the outcome
    method = models.CharField(max_length=10, blank=True, default="")
    tls_verified = models.BooleanField(null=True, blank=True, verbose_name="TLS Verified")
    stored = models.CharField(max_length=100, blank=True, default="",
                              help_text="Which credentials the mPCC stored for this BMC.")
    error = models.CharField(max_length=500, blank=True, default="")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    created = models.DateTimeField(auto_now_add=True)
    finished = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "BMC Credential Change"
        verbose_name_plural = "BMC Credential Changes"
        ordering = ("-created",)

    def __str__(self):
        return f"{self.bmc} {self.get_kind_display().lower()}"

    def clear_secrets(self, keep_candidates=False):
        self.current_password = self.new_password = ""
        if not keep_candidates:
            self.candidates = []
