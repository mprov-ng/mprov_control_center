""" Issuing an agent credential from a CSR (#381). """
from cryptography import x509
from django.db import transaction

from pki.ca import CA, check_csr, fingerprint
from pki.models import AgentCredential, service_user


def default_signer():
    from pki.signer_client import socket_signer
    return socket_signer


@transaction.atomic
def issue_credential(signer, csr_pem, lifetime, jobserver=None, system=None, image=None):
    """ Check the CSR, have it signed for a job server or a system, and
    record the credential.  signer is a callable (kind, name, lifetime, csr)
    -> PEM, normally the root signing helper's client; a CA signs in this
    process (tests).  Returns (credential, certificate PEM).  Raises PKIError
    for a bad CSR or a refused or failed signature. """
    if isinstance(signer, CA):
        from pki.signer_client import local_signer
        signer = local_signer(signer)
    if isinstance(csr_pem, bytes):
        csr_pem = csr_pem.decode(errors="replace")
    check_csr(csr_pem)
    user = service_user(jobserver, system, image)
    kind = (AgentCredential.JOBSERVER if jobserver is not None
            else AgentCredential.BUILD if image is not None else AgentCredential.SYSTEM)
    pem = signer(kind, user.username, lifetime, csr_pem)
    cert = x509.load_pem_x509_certificate(pem.encode())
    credential = AgentCredential.objects.create(
        kind=kind, jobserver=jobserver, system=system, image=image, user=user,
        serial=format(cert.serial_number, "x"), fingerprint=fingerprint(cert), certificate=pem,
        not_before=cert.not_valid_before_utc, not_after=cert.not_valid_after_utc,
    )
    return credential, pem
