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
- POST /enroll/recover/ {csr}: a system whose credential has expired, from
  one of its own addresses, while an admin has a re-enrollment window open
  for it ("Let these systems re-enroll" in the admin).
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
    AgentCredential.BUILD: datetime.timedelta(hours=2),
}
# how long before expiry an agent may renew
RENEW_WINDOW = {
    AgentCredential.JOBSERVER: datetime.timedelta(days=30),
    AgentCredential.SYSTEM: datetime.timedelta(days=15),
}


def _ca_pem():
    """ The CA certificate in PEM, or None before it exists. """
    from pki.authentication import ca_cert
    ca = ca_cert()
    return cert_pem(ca) if ca is not None else None


class EnrollBase(APIView):
    """ Shared by the enrollment views: refuses plain HTTP, signs a CSR through
    the root signing helper, and answers with the new certificate and the CA. """
    # the signer; tests swap in one that signs in-process
    signer = None

    def get_signer(self):
        """ The signer to use: the root signing helper's client, unless a test set one. """
        return self.signer or default_signer()

    def initial(self, request, *args, **kwargs):
        """ Note a refusal for a request that didn't come over HTTPS; each post()
        returns it first. """
        super().initial(request, *args, **kwargs)
        self.refusal = None
        if not request.is_secure():
            self.refusal = Response({"detail": "Enrollment needs HTTPS."}, status=status.HTTP_403_FORBIDDEN)

    def issued(self, credential, pem):
        """ The reply for a new credential: its certificate, the CA, its kind and
        expiry. """
        return Response({"certificate": pem, "ca": _ca_pem(), "kind": credential.kind,
                         "not_after": credential.not_after}, status=status.HTTP_200_OK)

    @staticmethod
    def revoke_others(keep, **agent):
        """ Revoke the agent's other active credentials, keeping keep. """
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
    """ Enroll a job server.

    POST {token, csr, host_id, name}, over HTTPS: a one-time enrollment token
    registers (or updates) the job server with this host ID and signs its CSR.
    Returns its certificate and the CA; its older credentials are revoked.
    403 for an unknown, used or expired token, 409 if the host ID conflicts,
    400 for a bad request. """
    def post(self, request):
        """ Redeem the token, register the job server and sign its CSR, all or
        nothing. """
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
        log.info(f"enrolled job server {jobserver.name} ({host_id}) with token {token.prefix}...")
        return self.issued(credential, pem)


class EnrollSystemView(EnrollView):
    """ Enroll a booting system.

    POST {nonce, csr}, over HTTPS, from the address that booted: the one-time
    nonce from its kernel command line signs its CSR.  Returns its certificate
    and the CA; its older credentials are revoked.  403 for an unknown, used or
    expired nonce, or one from another address. """
    def post(self, request):
        """ Redeem the nonce for the calling address and sign the system's CSR, all or
        nothing. """
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
        """ Sign a new certificate for the calling agent, once its current one is in
        its renewal window (409 before that). """
        if self.refusal:
            return self.refusal
        credential = request.auth if isinstance(request.auth, AgentCredential) else None
        if credential is None or credential.kind not in RENEW_WINDOW:
            return Response({"detail": "Renewal needs a job server's or system's current certificate."},
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


class RecoverView(EnrollView):
    """ A system re-enrolls through the window an admin opened for it.  The
    caller is the system its address belongs to; the window is the proof. """

    def post(self, request):
        if self.refusal:
            return self.refusal
        from common.permissions import system_from_address
        from systems.views_noauth import get_client_ip
        data = request.data if isinstance(request.data, dict) else {}
        if not isinstance(data.get("csr"), str):
            return Response({"csr": "Must be a PEM certificate signing request."}, status=status.HTTP_400_BAD_REQUEST)
        ip = get_client_ip(request)
        system = system_from_address(request)
        with transaction.atomic():
            if not BootNonce.redeem_recovery(system):
                who = system.hostname if system else "no known system"
                log.warning(f"re-enrollment from {ip} ({who}) refused: no window open")
                return Response({"detail": "No re-enrollment window is open for this system. An admin can open one: "
                                           "Systems, select it, \"Let these systems re-enroll\"."},
                                status=status.HTTP_403_FORBIDDEN)
            credential, pem, error = self.sign(data["csr"], LIFETIMES[AgentCredential.SYSTEM], system=system)
            if error:
                transaction.set_rollback(True)
                return error
            self.revoke_others(credential, system=system)
        log.info(f"re-enrolled {system.hostname} ({ip}) through an admin's window")
        return self.issued(credential, pem)


def ca_certificate(request):
    """ GET /enroll/ca.crt: the CA certificate in PEM, or 404 before it exists. """
    pem = _ca_pem()
    if pem is None:
        return HttpResponse("No CA yet.\n", status=404, content_type="text/plain")
    return HttpResponse(pem, content_type="application/x-pem-file")


class BuildCredentialView(EnrollBase):
    """ POST /enroll/build/ {csr, image}: a job server, with its own
    certificate, gets a 2-hour credential for the script runner inside an
    image it's building.  It reads only that image (pki.rules), and the job
    server deletes it before packing the image. """

    def post(self, request):
        """ Sign a short-lived credential for the named image, for a job server's
        certificate only. """
        if self.refusal:
            return self.refusal
        from systems.models import SystemImage
        credential = request.auth if isinstance(request.auth, AgentCredential) else None
        if credential is None or credential.kind != AgentCredential.JOBSERVER:
            return Response({"detail": "Needs a job server's certificate."}, status=status.HTTP_403_FORBIDDEN)
        data = request.data if isinstance(request.data, dict) else {}
        image = SystemImage.objects.filter(slug=data.get("image")).first() if isinstance(data.get("image"), str) else None
        if image is None:
            return Response({"image": "No such image."}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(data.get("csr"), str):
            return Response({"csr": "Must be a PEM certificate signing request."}, status=status.HTTP_400_BAD_REQUEST)
        new, pem, error = self.sign(data["csr"], LIFETIMES[AgentCredential.BUILD], image=image)
        if error:
            return error
        log.info(f"{credential.user.username} got a build credential for image {image.slug}")
        return self.issued(new, pem)
