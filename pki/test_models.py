import datetime
import os
import shutil
import tempfile
from io import StringIO
from unittest import mock

from cryptography import x509
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from common.testing import APITestCase
from jobqueue.models import JobServer
from pki.ca import CA, PKIError, fingerprint
from pki.issue import issue_credential
from pki.management.commands.mprov_tls import names_from_env
from pki.models import AgentCredential, service_user, service_username
from pki.test_ca import make_csr
from systems.models import System

DAY = datetime.timedelta(days=1)


class CredentialTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "admin@example.com", "password")
        self.ca = CA.create("test CA")
        self.js = JobServer.objects.create(name="js1", host_id="abc123")
        self.system = System.objects.create(hostname="c01", created_by=self.admin)


class ServiceUserTests(CredentialTestCase):
    """ #381: each agent's credentials act as its own service user. """

    def test_names(self):
        self.assertEqual(service_username(jobserver=self.js), "mprov.js.abc123")
        self.assertEqual(service_username(system=self.system), f"mprov.sys.{self.system.pk}")
        self.js.host_id = None
        self.assertEqual(service_username(jobserver=self.js), f"mprov.js.pk{self.js.pk}")
        with self.assertRaises(ValueError):
            service_username()
        with self.assertRaises(ValueError):
            service_username(self.js, self.system)

    def test_made_once_without_a_password_or_staff(self):
        user = service_user(system=self.system)
        self.assertEqual(service_user(system=self.system), user)
        self.assertFalse(user.has_usable_password())
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.first_name, "c01")


class IssueCredentialTests(CredentialTestCase):
    """ #381: a signed CSR is recorded as an AgentCredential. """

    def test_job_server(self):
        credential, pem = issue_credential(self.ca, make_csr(), 90 * DAY, jobserver=self.js)
        cert = x509.load_pem_x509_certificate(pem.encode())
        self.assertEqual(credential.kind, "jobserver")
        self.assertEqual(credential.agent, self.js)
        self.assertEqual(credential.user.username, "mprov.js.abc123")
        self.assertEqual(credential.fingerprint, fingerprint(cert))
        self.assertEqual(credential.serial, format(cert.serial_number, "x"))
        self.assertEqual(credential.not_after, cert.not_valid_after_utc)
        self.assertTrue(credential.is_active())
        self.assertEqual(list(self.js.credentials.all()), [credential])

    def test_system(self):
        credential, _ = issue_credential(self.ca, make_csr(), 30 * DAY, system=self.system)
        self.assertEqual(credential.kind, "system")
        self.assertEqual(credential.agent, self.system)

    def test_a_bad_csr_records_nothing(self):
        with self.assertRaises(PKIError):
            issue_credential(self.ca, b"junk", DAY, system=self.system)
        self.assertFalse(AgentCredential.objects.exists())

    def test_exactly_one_agent(self):
        credential, _ = issue_credential(self.ca, make_csr(), DAY, system=self.system)
        for kind, js, system in (("system", self.js, self.system), ("system", None, None), ("jobserver", None, self.system)):
            with self.subTest(kind=kind, js=js, system=system):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    AgentCredential.objects.filter(pk=credential.pk).update(kind=kind, jobserver=js, system=system)

    def test_active_revoked_expired(self):
        credential, _ = issue_credential(self.ca, make_csr(), DAY, system=self.system)
        now = timezone.now()
        self.assertEqual(list(AgentCredential.objects.active()), [credential])
        self.assertFalse(credential.is_active(now + 2 * DAY))
        self.assertFalse(AgentCredential.objects.active(now + 2 * DAY).exists())
        credential.revoke()
        first = credential.revoked_at
        credential.revoke()
        self.assertEqual(AgentCredential.objects.get().revoked_at, first)
        self.assertFalse(credential.is_active())
        self.assertFalse(AgentCredential.objects.active().exists())

    def test_deleting_the_agent_removes_its_credentials(self):
        issue_credential(self.ca, make_csr(), DAY, system=self.system)
        issue_credential(self.ca, make_csr(), DAY, jobserver=self.js)
        self.system.delete()
        self.js.delete()
        self.assertFalse(AgentCredential.objects.exists())


class AgentCredentialAdminTests(APITestCase):
    """ #381: the admin lists credentials read-only, and can revoke them. """

    def setUp(self):
        super().setUp()
        system = System.objects.create(hostname="c01", created_by=self.user)
        self.credential, _ = issue_credential(CA.create("test CA"), make_csr(), DAY, system=system)

    def test_changelist_and_no_add(self):
        page = self.client.get("/admin/pki/agentcredential/")
        self.assertContains(page, "mprov.sys.")
        self.assertEqual(self.client.get("/admin/pki/agentcredential/add/").status_code, 403)

    def test_change_page_is_read_only(self):
        page = self.client.get(f"/admin/pki/agentcredential/{self.credential.pk}/change/")
        self.assertContains(page, self.credential.fingerprint)
        self.assertNotContains(page, 'name="fingerprint"')

    def test_revoke_action(self):
        response = self.client.post("/admin/pki/agentcredential/", {
            "action": "revoke", "_selected_action": [self.credential.pk]}, follow=True)
        self.assertContains(response, "Revoked 1 credential.")
        self.assertIsNotNone(AgentCredential.objects.get().revoked_at)


class MprovTLSCommandTests(TestCase):
    """ #381: init_mpcc.sh runs `manage.py mprov_tls --shell` before Apache starts. """

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def run_command(self, env, *args):
        out, err = StringIO(), StringIO()
        with mock.patch.dict(os.environ, env, clear=False), mock.patch("sys.stderr", err):
            for var in ("MPROV_TLS_CERT", "MPROV_TLS_KEY"):
                if var not in env:
                    os.environ.pop(var, None)
            call_command("mprov_tls", "--dir", self.dir, *args, stdout=out)
        return out.getvalue(), err.getvalue()

    def test_shell_exports_only(self):
        out, err = self.run_command({"MPROV_MPCC_HOSTNAME": "mpcc", "MPROV_MPCC_IPs": "10.1.2.1"}, "--shell")
        self.assertEqual(out.splitlines(), [
            f"export MPROV_TLS_CERT={self.dir}/server.crt",
            f"export MPROV_TLS_KEY={self.dir}/server.key",
            f"export MPROV_TLS_CA={self.dir}/ca.crt",
        ])
        self.assertIn("Made a new CA", err)
        self.assertIn("mProv CA (mpcc)", CA.load(self.dir).cert.subject.rfc4514_string())

    def test_errors_stop_the_start(self):
        with self.assertRaisesRegex(CommandError, "TLS setup failed: set both"):
            self.run_command({"MPROV_TLS_CERT": "/nope.crt"}, "--shell")

    def test_names_from_env(self):
        self.assertEqual(names_from_env({"MPROV_MPCC_HOSTNAME": "mpcc", "MPROV_DOMAINNAME": "example.com",
                                         "MPROV_MPCC_IPs": "10.1.2.1, 10.1.3.1"}),
                         (["mpcc", "mpcc.example.com", "localhost"], ["10.1.2.1", "10.1.3.1", "127.0.0.1"]))
        with mock.patch("socket.getfqdn", return_value="box.example.com"):
            self.assertEqual(names_from_env({}), (["box.example.com", "localhost"], ["127.0.0.1"]))
