""" Enrollment (#381): how job servers and booted systems get their client
certificates.

- POST /enroll/jobserver/ {token, csr, host_id, name}: a job server with a
  one-time enrollment token (made in the admin, or by init_mpcc.sh for the job
  server in the same compose stack).
- POST /enroll/system/ {nonce, csr}: a booting system, with the one-time
  nonce /ipxe/ put on its kernel command line (mprov_enroll=...), from the
  address that booted.
- POST /enroll/renew/ {csr}: an agent, authenticated with its current
  certificate, in the last part of that certificate's life.
- GET /enroll/ca.crt: the CA certificate, which agents check against the
  fingerprint they were given (mprov_ca= on the kernel command line, or next
  to the token) before trusting it.

Enrollment and renewal need HTTPS.  Each reply is {"certificate", "ca"}.  The
agent's key never leaves it: it sends a CSR.  Enrolling again revokes the
agent's older credentials.
"""
import datetime
import logging

from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from pki.ca import PKIError, cert_pem
from pki.issue import default_signer, issue_credential
from pki.models import AgentCredential, BootNonce, EnrollmentToken

log = logging.getLogger("mprov.enroll")

LIFETIMES = {
    AgentCredential.JOBSERVER: datetime.timedelta(days=90),
    AgentCredential.SYSTEM: datetime.timedelta(days=30),
}
# how long before expiry an agent may renew
RENEW_WINDOW = {
    AgentCredential.JOBSERVER: datetime.timedelta(days=30),
    AgentCredential.SYSTEM: datetime.timedelta(days=15),
}


def _ca_pem():
    from pki.authentication import ca_cert
    ca = ca_cert()
    return cert_pem(ca) if ca is not None else None


class EnrollBase(APIView):
    # the signer; tests swap in one that signs in-process
    signer = None

    def get_signer(self):
        return self.signer or default_signer()

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.refusal = None
        if not request.is_secure():
            self.refusal = Response({"detail": "Enrollment needs HTTPS."}, status=status.HTTP_403_FORBIDDEN)

    def issued(self, credential, pem):
        return Response({"certificate": pem, "ca": _ca_pem(), "kind": credential.kind,
                         "not_after": credential.not_after}, status=status.HTTP_200_OK)

    @staticmethod
    def revoke_others(keep, **agent):
        AgentCredential.objects.filter(revoked_at__isnull=True, **agent).exclude(pk=keep.pk).update(
            revoked_at=timezone.now())

    def sign(self, csr, lifetime, **agent):
        """ (credential, pem, None) or (None, None, error Response). """
        try:
            credential, pem = issue_credential(self.get_signer(), csr, lifetime, **agent)
        except PKIError as e:
            from pki.signer_client import SignerUnavailable
            if isinstance(e, SignerUnavailable):
                log.error(f"enrollment failed: {e}")
                return None, None, Response({"detail": "The mPCC can't sign right now; try again."},
                                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
            return None, None, Response({"csr": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return credential, pem, None


class EnrollView(EnrollBase):
    """ Unauthenticated: the token or nonce is the proof. """
    authentication_classes = []
    permission_classes = []


class EnrollJobServerView(EnrollView):
    def post(self, request):
        if self.refusal:
            return self.refusal
        data = request.data if isinstance(request.data, dict) else {}
        host_id, name = data.get("host_id"), data.get("name")
        errors = {}
        if not (isinstance(host_id, str) and 0 < len(host_id.strip()) <= 64):
            errors["host_id"] = "Must be a non-blank string of up to 64 characters."
        if not (isinstance(name, str) and 0 < len(name.strip()) <= 255):
            errors["name"] = "Must be a non-blank string of up to 255 characters."
        if not isinstance(data.get("csr"), str):
            errors["csr"] = "Must be a PEM certificate signing request."
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        from jobqueue.views import JobServersAPIView
        with transaction.atomic():
            token = EnrollmentToken.redeem(data.get("token"))
            if token is None:
                log.warning(f"job server enrollment refused for {name} ({host_id}): unknown, used or expired token")
                return Response({"token": "Unknown, used or expired."}, status=status.HTTP_403_FORBIDDEN)
            jobserver, conflict = JobServersAPIView()._register_by_host_id(host_id.strip(), {"name": name.strip()})
            if conflict:
                transaction.set_rollback(True)
                return Response({"detail": conflict}, status=status.HTTP_409_CONFLICT)
            credential, pem, error = self.sign(data["csr"], LIFETIMES[AgentCredential.JOBSERVER], jobserver=jobserver)
            if error:
                transaction.set_rollback(True)
                return error
            token.jobserver = jobserver
            token.save(update_fields=["jobserver"])
            self.revoke_others(credential, jobserver=jobserver)
        log.info(f"enrolled job server {jobserver.name} ({host_id}) with token {token.prefix}…")
        return self.issued(credential, pem)


class EnrollSystemView(EnrollView):
    def post(self, request):
        if self.refusal:
            return self.refusal
        from systems.views_noauth import get_client_ip
        data = request.data if isinstance(request.data, dict) else {}
        if not isinstance(data.get("csr"), str):
            return Response({"csr": "Must be a PEM certificate signing request."}, status=status.HTTP_400_BAD_REQUEST)
        ip = get_client_ip(request)
        with transaction.atomic():
            system, reason = BootNonce.redeem(data.get("nonce"), ip)
            if system is None:
                # a used nonce means someone raced the node to it: say so loudly.
                level = logging.ERROR if "already used" in reason else logging.WARNING
                log.log(level, f"system enrollment from {ip} refused: {reason}")
                return Response({"nonce": "Unknown, used, expired or from another address."},
                                status=status.HTTP_403_FORBIDDEN)
            credential, pem, error = self.sign(data["csr"], LIFETIMES[AgentCredential.SYSTEM], system=system)
            if error:
                transaction.set_rollback(True)
                return error
            # a new boot, so the system's older credentials go
            self.revoke_others(credential, system=system)
        log.info(f"enrolled {system.hostname} ({ip})")
        return self.issued(credential, pem)


class RenewView(EnrollBase):
    """ Authenticated with the agent's current certificate (pki.rules lets
    both kinds POST here), with the project's default classes. """

    def post(self, request):
        if self.refusal:
            return self.refusal
        credential = request.auth if isinstance(request.auth, AgentCredential) else None
        if credential is None:
            return Response({"detail": "Renewal needs the agent's current certificate."},
                            status=status.HTTP_403_FORBIDDEN)
        data = request.data if isinstance(request.data, dict) else {}
        if not isinstance(data.get("csr"), str):
            return Response({"csr": "Must be a PEM certificate signing request."}, status=status.HTTP_400_BAD_REQUEST)
        if credential.not_after - timezone.now() > RENEW_WINDOW[credential.kind]:
            return Response({"detail": f"Not due: renew from {credential.not_after - RENEW_WINDOW[credential.kind]:%Y-%m-%d}."},
                            status=status.HTTP_409_CONFLICT)
        agent = {"jobserver": credential.jobserver} if credential.kind == AgentCredential.JOBSERVER \
            else {"system": credential.system}
        new, pem, error = self.sign(data["csr"], LIFETIMES[credential.kind], **agent)
        if error:
            return error
        log.info(f"renewed {credential.user.username}: serial {new.serial}")
        return self.issued(new, pem)


def ca_certificate(request):
    pem = _ca_pem()
    if pem is None:
        return HttpResponse("No CA yet.\n", status=404, content_type="text/plain")
    return HttpResponse(pem, content_type="application/x-pem-file")
