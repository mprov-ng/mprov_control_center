import datetime
import os
import re
import shutil
import tempfile
import threading
from io import StringIO
from unittest import mock

from cryptography import x509
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from jobqueue.models import JobServer
from mprov_control_center.version import API_VERSION
from osmanagement.models import OSDistro
from pki import signer as signer_module
from pki.ca import CA, PKIError, fingerprint, issued_by
from pki.issue import issue_credential
from pki.models import AgentCredential, BootNonce, EnrollmentToken
from pki.signer_client import SignerUnavailable, local_signer, socket_signer
from pki.test_ca import make_csr
from pki.views import EnrollBase
from systems.models import NetworkInterface, System, SystemImage

DAY = datetime.timedelta(days=1)


def csr_text():
    return make_csr().decode()


class SignerPolicyTests(SimpleTestCase):
    """ #381: the signing helper signs only what its policy allows. """

    def setUp(self):
        self.ca = CA.create("test CA")

    def sign(self, **request):
        return signer_module.handle(self.ca, {"kind": "system", "name": "mprov.sys.7", "lifetime": 3600,
                                              "csr": csr_text(), **request})

    def test_signs_a_good_request(self):
        reply = self.sign()
        cert = x509.load_pem_x509_certificate(reply["certificate"].encode())
        self.assertTrue(issued_by(cert, self.ca.cert))

    def test_lifetime_is_capped_per_kind(self):
        for kind, name, cap in (("system", "mprov.sys.7", 30 * DAY), ("jobserver", "mprov.js.abc", 90 * DAY),
                                ("build", "mprov.build.compute", datetime.timedelta(hours=2))):
            with self.subTest(kind=kind):
                reply = self.sign(kind=kind, name=name, lifetime=10 ** 9)
                cert = x509.load_pem_x509_certificate(reply["certificate"].encode())
                life = cert.not_valid_after_utc - cert.not_valid_before_utc
                self.assertLessEqual(life, cap + datetime.timedelta(hours=1, seconds=1))

    def test_refusals(self):
        for request in ({"kind": "admin"}, {"name": "admin"}, {"name": "mprov.js.abc"},
                        {"name": "mprov.sys.7; rm"}, {"lifetime": 0}, {"lifetime": -5}, {"lifetime": "1"},
                        {"lifetime": True}, {"csr": "junk"}, {"csr": None}):
            with self.subTest(request=request):
                self.assertIn("error", self.sign(**request))
        self.assertIn("error", signer_module.handle(self.ca, ["not", "a", "dict"]))


class SignerSocketTests(SimpleTestCase):
    """ #381: Django reaches the helper over its Unix socket. """

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        CA.create("test CA").save(self.dir)
        self.path = os.path.join(self.dir, "run", "signer.sock")
        thread = threading.Thread(target=signer_module.serve, args=(self.dir, self.path, ""), daemon=True)
        thread.start()
        for _ in range(100):
            if os.path.exists(self.path):
                break
            threading.Event().wait(0.02)

    def test_round_trip(self):
        pem = socket_signer("system", "mprov.sys.7", DAY, csr_text(), path=self.path)
        self.assertTrue(issued_by(x509.load_pem_x509_certificate(pem.encode()), CA.load(self.dir).cert))
        self.assertEqual(oct(os.stat(self.path).st_mode & 0o777), "0o660")

    def test_refusal_is_a_pki_error(self):
        with self.assertRaisesRegex(PKIError, "unknown kind"):
            socket_signer("admin", "x", DAY, csr_text(), path=self.path)

    def test_unreachable(self):
        with self.assertRaises(SignerUnavailable):
            socket_signer("system", "mprov.sys.7", DAY, csr_text(), path=os.path.join(self.dir, "nope.sock"))

    def test_no_ca_no_helper(self):
        with self.assertRaises(SystemExit):
            signer_module.serve(tempfile.mkdtemp(dir=self.dir), os.path.join(self.dir, "x.sock"), "")


class TokenAndNonceTests(TestCase):
    """ #381: enrollment tokens and boot nonces are one-time, short-lived and stored hashed. """

    def setUp(self):
        self.user = User.objects.create_superuser("admin", "a@example.com", "password")
        self.system = System.objects.create(hostname="c01", created_by=self.user)

    def test_token_once(self):
        row, secret = EnrollmentToken.make()
        self.assertNotIn(secret, row.token_hash)
        self.assertEqual(EnrollmentToken.redeem(secret), row)
        self.assertIsNone(EnrollmentToken.redeem(secret))
        self.assertIsNone(EnrollmentToken.redeem(""))
        self.assertIsNone(EnrollmentToken.redeem(None))

    def test_token_expires(self):
        _, secret = EnrollmentToken.make(datetime.timedelta(seconds=-1))
        self.assertIsNone(EnrollmentToken.redeem(secret))

    def test_nonce_rules(self):
        nonce = BootNonce.issue(self.system, "10.0.0.20")
        self.assertEqual(BootNonce.redeem(nonce, "10.0.0.21"), (None, f"nonce for c01 sent from 10.0.0.21, not 10.0.0.20"))
        self.assertEqual(BootNonce.redeem(nonce, "10.0.0.20"), (self.system, None))
        self.assertEqual(BootNonce.redeem(nonce, "10.0.0.20"), (None, "nonce already used for c01"))
        self.assertEqual(BootNonce.redeem("nope", "10.0.0.20"), (None, "unknown nonce"))

    def test_nonce_expires(self):
        nonce = BootNonce.issue(self.system, "10.0.0.20")
        BootNonce.objects.update(expires=timezone.now() - DAY)
        self.assertEqual(BootNonce.redeem(nonce, "10.0.0.20"), (None, "nonce for c01 expired"))

    def test_a_new_boot_drops_unused_nonces(self):
        old = BootNonce.issue(self.system, "10.0.0.20")
        BootNonce.issue(self.system, "10.0.0.20")
        self.assertEqual(BootNonce.redeem(old, "10.0.0.20"), (None, "unknown nonce"))


class EnrollTestCase(TestCase):
    def setUp(self):
        self.tls_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tls_dir, True)
        overrides = override_settings(MPROV_TLS_DIR=self.tls_dir, MPROV_SKIP_VERSION_CHECK=False)
        overrides.enable()
        self.addCleanup(overrides.disable)
        self.ca = CA.create("test CA")
        self.ca.save(self.tls_dir)
        patcher = mock.patch.object(EnrollBase, "signer", staticmethod(local_signer(self.ca)))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.user = User.objects.create_superuser("admin", "a@example.com", "password")
        distro = OSDistro.objects.create(name="d", vendor="v", version="9", baseurl="http://localhost/",
                                         install_kernel_cmdline="quiet", initial_mods="e1000",
                                         prov_interface="eth0", tmpfs_root_size=8)
        self.image = SystemImage.objects.create(name="compute", created_by=self.user, osdistro=distro)
        self.system = System.objects.create(hostname="c01", created_by=self.user, systemimage=self.image)
        NetworkInterface.objects.create(system=self.system, name="eth0", ipaddress="10.0.0.20", bootable=True)

    def post(self, url, body, ip="10.0.0.20", secure=True, **extra):
        return self.client.post(url, body, content_type="application/json", REMOTE_ADDR=ip, secure=secure, **extra)

    def cert(self, response):
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(fingerprint(x509.load_pem_x509_certificate(body["ca"].encode())), fingerprint(self.ca.cert))
        cert = x509.load_pem_x509_certificate(body["certificate"].encode())
        self.assertTrue(issued_by(cert, self.ca.cert))
        return cert


class JobServerEnrollTests(EnrollTestCase):
    """ #381: a job server enrolls with a one-time token. """

    def enroll(self, secret, host_id="host-abc", name="js1", **kwargs):
        return self.post("/enroll/jobserver/", {"token": secret, "csr": csr_text(), "host_id": host_id,
                                                "name": name}, **kwargs)

    def test_enrolls_and_registers(self):
        row, secret = EnrollmentToken.make()
        cert = self.cert(self.enroll(secret))
        js = JobServer.objects.get(host_id="host-abc")
        credential = AgentCredential.objects.get()
        self.assertEqual((credential.jobserver, credential.fingerprint), (js, fingerprint(cert)))
        row.refresh_from_db()
        self.assertEqual(row.jobserver, js)
        self.assertIsNotNone(row.used_at)
        self.assertLessEqual(cert.not_valid_after_utc - timezone.now(), 90 * DAY)

    def test_the_log_line_is_ascii(self):
        # #530: mod_wsgi escapes non-ASCII on stderr, so a "…" showed up in
        # Apache's error log as \xe2\x80\xa6.
        row, secret = EnrollmentToken.make()
        with self.assertLogs("mprov.enroll", "INFO") as logs:
            self.cert(self.enroll(secret))
        line = next(m for m in logs.output if "enrolled job server js1" in m)
        self.assertIn(f"with token {row.prefix}...", line)
        self.assertTrue(line.isascii(), line)

    def test_the_token_works_once(self):
        _, secret = EnrollmentToken.make()
        self.cert(self.enroll(secret))
        self.assertEqual(self.enroll(secret).status_code, 403)
        self.assertEqual(self.enroll("guess").status_code, 403)

    def test_needs_https(self):
        _, secret = EnrollmentToken.make()
        response = self.enroll(secret, secure=False)
        self.assertEqual(response.status_code, 403)
        self.assertIn("HTTPS", response.json()["detail"])
        self.assertTrue(EnrollmentToken.objects.get().usable())

    def test_bad_requests_keep_the_token(self):
        _, secret = EnrollmentToken.make()
        JobServer.objects.create(name="taken", host_id="other-host")
        self.assertEqual(self.enroll(secret, host_id="").status_code, 400)
        self.assertEqual(self.enroll(secret, name="taken").status_code, 409)
        bad_csr = self.post("/enroll/jobserver/", {"token": secret, "csr": "junk", "host_id": "h", "name": "n"})
        self.assertEqual(bad_csr.status_code, 400)
        self.assertTrue(EnrollmentToken.objects.get().usable())
        self.assertFalse(AgentCredential.objects.exists())

    def test_enrolling_again_revokes_the_old_credential(self):
        _, first = EnrollmentToken.make()
        _, second = EnrollmentToken.make()
        self.cert(self.enroll(first))
        self.cert(self.enroll(second))
        self.assertEqual(AgentCredential.objects.active().count(), 1)
        self.assertEqual(AgentCredential.objects.count(), 2)

    def test_signer_down_is_503_and_keeps_the_token(self):
        _, secret = EnrollmentToken.make()

        def down(*args):
            raise SignerUnavailable("nope")
        with mock.patch.object(EnrollBase, "signer", staticmethod(down)):
            self.assertEqual(self.enroll(secret).status_code, 503)
        self.assertTrue(EnrollmentToken.objects.get().usable())


class SystemEnrollTests(EnrollTestCase):
    """ #381: a booting system enrolls with the nonce /ipxe/ gave it. """

    def ipxe_params(self, ip="10.0.0.20"):
        content = self.client.get("/ipxe/", REMOTE_ADDR=ip).content.decode()
        nonce = re.search(r"mprov_enroll=([0-9a-f]+)", content)
        ca = re.search(r"mprov_ca=([0-9a-f]+)", content)
        return (nonce.group(1) if nonce else None), (ca.group(1) if ca else None)

    def enroll(self, nonce, ip="10.0.0.20"):
        return self.post("/enroll/system/", {"nonce": nonce, "csr": csr_text()}, ip=ip)

    def test_ipxe_gives_a_nonce_and_the_ca_fingerprint(self):
        nonce, ca = self.ipxe_params()
        self.assertEqual(ca, fingerprint(self.ca.cert))
        cert = self.cert(self.enroll(nonce))
        self.assertEqual(AgentCredential.objects.get().system, self.system)
        self.assertLessEqual(cert.not_valid_after_utc - timezone.now(), 30 * DAY)

    def test_the_nonce_works_once_from_its_address(self):
        nonce, _ = self.ipxe_params()
        self.assertEqual(self.enroll(nonce, ip="10.0.0.99").status_code, 403)
        self.cert(self.enroll(nonce))
        with self.assertLogs("mprov.enroll", "ERROR") as logs:
            self.assertEqual(self.enroll(nonce).status_code, 403)
        self.assertIn("nonce already used for c01", logs.output[0])

    def test_a_new_boot_revokes_the_last_one(self):
        self.cert(self.enroll(self.ipxe_params()[0]))
        self.cert(self.enroll(self.ipxe_params()[0]))
        self.assertEqual(AgentCredential.objects.active().count(), 1)

    def test_no_nonce_for_a_local_boot_or_without_a_ca(self):
        System.objects.filter(pk=self.system.pk).update(provision=False)
        self.assertEqual(self.ipxe_params(), (None, None))
        System.objects.filter(pk=self.system.pk).update(provision=True)
        shutil.rmtree(self.tls_dir)
        self.assertEqual(self.ipxe_params(), (None, None))

    def test_ca_certificate_download(self):
        response = self.client.get("/enroll/ca.crt")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(fingerprint(x509.load_pem_x509_certificate(response.content)), fingerprint(self.ca.cert))
        shutil.rmtree(self.tls_dir)
        self.assertEqual(self.client.get("/enroll/ca.crt").status_code, 404)


class RenewTests(EnrollTestCase):
    """ #381: an agent renews with its current certificate, near expiry. """

    def setUp(self):
        super().setUp()
        self.js = JobServer.objects.create(name="js1", host_id="host-abc")
        self.cred, self.pem = issue_credential(self.ca, make_csr(), 90 * DAY, jobserver=self.js)

    def renew(self, pem=None, ip="10.0.0.5"):
        meta = {"HTTP_MPROV_VERSION": API_VERSION}
        if pem:
            meta.update(SSL_CLIENT_CERT=pem, SSL_CLIENT_VERIFY="SUCCESS")
        return self.post("/enroll/renew/", {"csr": csr_text()}, ip=ip, **meta)

    def test_not_due_yet(self):
        self.assertEqual(self.renew(self.pem).status_code, 409)

    def test_renews_in_its_window(self):
        AgentCredential.objects.filter(pk=self.cred.pk).update(not_after=timezone.now() + 10 * DAY)
        cert = self.cert(self.renew(self.pem))
        new = AgentCredential.objects.get(fingerprint=fingerprint(cert))
        self.assertEqual(new.jobserver, self.js)
        # the old one stays until it expires, so a crash mid-swap doesn't lock it out
        self.assertTrue(AgentCredential.objects.get(pk=self.cred.pk).is_active())

    def test_a_system_renews_too(self):
        system_cred, pem = issue_credential(self.ca, make_csr(), 30 * DAY, system=self.system)
        AgentCredential.objects.filter(pk=system_cred.pk).update(not_after=timezone.now() + 5 * DAY)
        self.cert(self.renew(pem, ip="10.0.0.20"))

    def test_needs_a_certificate(self):
        self.assertIn(self.renew().status_code, (401, 403))
        self.client.force_login(self.user)
        self.assertEqual(self.renew().status_code, 403)


class BootstrapTokenTests(TestCase):
    """ #381: init_mpcc.sh leaves a token for the local job server until one has enrolled. """

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.path = os.path.join(self.dir, "enroll_token")

    def bootstrap(self):
        call_command("mprov_enroll_token", "--bootstrap", self.path, stderr=StringIO())

    def test_writes_one_and_keeps_it(self):
        self.bootstrap()
        secret = open(self.path).read().strip()
        self.assertEqual(oct(os.stat(self.path).st_mode & 0o777), "0o600")
        self.bootstrap()
        self.assertEqual(open(self.path).read().strip(), secret)
        self.assertEqual(EnrollmentToken.objects.count(), 1)

    def test_replaces_a_used_one(self):
        self.bootstrap()
        EnrollmentToken.redeem(open(self.path).read().strip())
        self.bootstrap()
        self.assertEqual(EnrollmentToken.objects.count(), 2)

    def test_none_once_a_job_server_has_enrolled(self):
        js = JobServer.objects.create(name="js1", host_id="h")
        issue_credential(CA.create("x"), make_csr(), DAY, jobserver=js)
        self.bootstrap()
        self.assertFalse(os.path.exists(self.path))

    def test_plain_command_prints_one(self):
        out = StringIO()
        call_command("mprov_enroll_token", "--note", "js2", stdout=out)
        self.assertIn("token: ", out.getvalue())
        self.assertEqual(EnrollmentToken.objects.get().note, "js2")


class EnrollmentTokenAdminTests(TestCase):
    """ #381: a token added in the admin is shown once. """

    def setUp(self):
        self.user = User.objects.create_superuser("admin", "a@example.com", "password")
        self.client.force_login(self.user)

    def test_add_shows_it_once(self):
        response = self.client.post("/admin/pki/enrollmenttoken/add/", {"note": "js9", "hours": 2}, follow=True)
        self.assertContains(response, "shown only this once")
        secret = re.search(r"shown only this once: <code>([^<]+)</code>", response.content.decode()).group(1)
        row = EnrollmentToken.objects.get()
        self.assertEqual((row.note, row.created_by), ("js9", self.user))
        self.assertLessEqual(row.expires - timezone.now(), datetime.timedelta(hours=2))
        self.assertEqual(EnrollmentToken.redeem(secret), row)
        page = self.client.get(f"/admin/pki/enrollmenttoken/{row.pk}/change/")
        self.assertNotContains(page, secret)
