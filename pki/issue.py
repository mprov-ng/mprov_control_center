""" Issuing an agent credential from a CSR (#381). """
from django.db import transaction

from pki.ca import check_csr, cert_pem, fingerprint
from pki.models import AgentCredential, service_user


@transaction.atomic
def issue_credential(ca, csr_pem, lifetime, jobserver=None, system=None, now=None):
    """ Check the CSR, sign it for a job server or a system, and record the
    credential.  Returns (credential, certificate PEM).  Raises PKIError for
    a bad CSR. """
    csr = check_csr(csr_pem)
    user = service_user(jobserver, system)
    kind = AgentCredential.JOBSERVER if jobserver is not None else AgentCredential.SYSTEM
    cert = ca.sign_csr(csr, user.username, kind, lifetime, now)
    pem = cert_pem(cert)
    credential = AgentCredential.objects.create(
        kind=kind, jobserver=jobserver, system=system, user=user,
        serial=format(cert.serial_number, "x"), fingerprint=fingerprint(cert), certificate=pem,
        not_before=cert.not_valid_before_utc, not_after=cert.not_valid_after_utc,
    )
    return credential, pem
