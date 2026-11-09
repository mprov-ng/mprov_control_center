import datetime
import json
import os
import tempfile

from django.test import SimpleTestCase
from django.utils import timezone

from pki.ca import CA, cert_pem, check_csr
from pki.issue import issue_credential
from pki.models import AgentCredential, BootNonce
from pki.test_ca import make_csr
from pki.test_enroll import DAY, EnrollTestCase, csr_text
from pki.test_node_enroll import Reply, load_enroll_module
from systems.models import System, SystemGroup


class RecoveryWindowTests(EnrollTestCase):
    """ #506: an admin opens a re-enrollment window for a system whose
    credential has expired, and the system enrolls through it from one of
    its own addresses. """

    def recover(self, ip="10.0.0.20", secure=True):
        return self.post("/enroll/recover/", {"csr": csr_text()}, ip=ip, secure=secure)

    def test_no_window_no_credential(self):
        with self.assertLogs("mprov.enroll", "WARNING") as logs:
            self.assertEqual(self.recover().status_code, 403)
        self.assertIn("(c01) refused: no window open", logs.output[0])

    def test_through_an_open_window_once(self):
        old, _ = issue_credential(self.ca, make_csr(), 30 * DAY, system=self.system)
        BootNonce.open_recovery(self.system, self.user)
        with self.assertLogs("mprov.enroll", "INFO") as logs:
            cert = self.cert(self.recover())
        self.assertIn("re-enrolled c01 (10.0.0.20)", logs.output[-1])
        new = AgentCredential.objects.get(revoked_at__isnull=True)
        self.assertEqual((new.system, new.kind), (self.system, AgentCredential.SYSTEM))
        self.assertLessEqual(cert.not_valid_after_utc - timezone.now(), 30 * DAY)
        self.assertIsNotNone(AgentCredential.objects.get(pk=old.pk).revoked_at)
        self.assertEqual(self.recover().status_code, 403)

    def test_only_from_the_systems_own_address(self):
        BootNonce.open_recovery(self.system)
        self.assertEqual(self.recover(ip="10.0.0.99").status_code, 403)
        # the window stays open for the system itself
        self.cert(self.recover())

    def test_the_window_closes(self):
        BootNonce.open_recovery(self.system)
        BootNonce.objects.filter(recovery=True).update(expires=timezone.now() - datetime.timedelta(seconds=1))
        self.assertEqual(self.recover().status_code, 403)

    def test_needs_https(self):
        BootNonce.open_recovery(self.system)
        self.assertEqual(self.recover(secure=False).status_code, 403)
        self.assertTrue(BootNonce.objects.filter(recovery=True, used_at__isnull=True).exists())

    def test_a_boot_keeps_an_open_window(self):
        BootNonce.open_recovery(self.system)
        nonce = BootNonce.issue(self.system, "10.0.0.20")
        self.assertTrue(BootNonce.objects.filter(recovery=True, used_at__isnull=True).exists())
        # and a window isn't a boot nonce
        self.assertEqual(BootNonce.redeem(nonce, "10.0.0.20")[0], self.system)
        self.assertEqual(BootNonce.redeem("0" * 32, "10.0.0.20")[0], None)

    def test_renewal_needs_no_version_header(self):
        """ A node's renewal helper is baked into its image, so /enroll/ isn't
        version-locked; the rest of the API still is. """
        credential, pem = issue_credential(self.ca, make_csr(), 30 * DAY, system=self.system)
        AgentCredential.objects.filter(pk=credential.pk).update(not_after=timezone.now() + 5 * DAY)
        meta = {"SSL_CLIENT_CERT": pem, "SSL_CLIENT_VERIFY": "SUCCESS"}
        self.cert(self.post("/enroll/renew/", {"csr": csr_text()}, **meta))
        response = self.client.get("/systembmcs/", REMOTE_ADDR="10.0.0.20", secure=True,
                                   CONTENT_TYPE="application/json", **meta)
        self.assertEqual(response.status_code, 426)

    def test_what_the_renewal_helper_relies_on(self):
        """ #532: mprov_enroll.py renew asks every time, without a version
        header: 409 when the credential isn't due, 401 with the client
        certificate challenge once it's revoked. """
        credential, pem = issue_credential(self.ca, make_csr(), 30 * DAY, system=self.system)
        meta = {"SSL_CLIENT_CERT": pem, "SSL_CLIENT_VERIFY": "SUCCESS"}
        self.assertEqual(self.post("/enroll/renew/", {"csr": csr_text()}, **meta).status_code, 409)
        credential.revoke()
        with self.assertLogs("mprov", "WARNING"):
            response = self.post("/enroll/renew/", {"csr": csr_text()}, **meta)
        self.assertEqual(response.status_code, 401)
        self.assertIn("TLS-Client-Certificate", response["WWW-Authenticate"])
        # and the window the admin opens takes the node back
        BootNonce.open_recovery(self.system)
        self.cert(self.recover())


class ReenrollAdminTests(EnrollTestCase):
    """ #506: the admin action that opens the windows, and the Credential
    line on the System page. """

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.c02 = System.objects.create(hostname="c02", created_by=self.user, systemimage=self.image)

    def test_on_systems(self):
        with self.assertLogs("mprov.enroll", "INFO") as logs:
            response = self.client.post("/admin/systems/system/", {
                "action": "reenroll", "_selected_action": [self.system.pk, self.c02.pk]}, follow=True)
        self.assertContains(response, "2 systems can re-enroll once")
        self.assertIn("admin opened a re-enrollment window for 2 systems", logs.output[0])
        windows = BootNonce.objects.filter(recovery=True)
        self.assertEqual(sorted(w.system.hostname for w in windows), ["c01", "c02"])
        self.assertTrue(all(w.opened_by == self.user for w in windows))

    def test_on_groups(self):
        group = SystemGroup.objects.create(name="rack1")
        group.systems.add(self.c02)
        response = self.client.post("/admin/systems/systemgroup/", {"action": "reenroll", "_selected_action": [group.pk]},
                                    follow=True)
        self.assertContains(response, "1 system can re-enroll once")
        self.assertEqual([w.system for w in BootNonce.objects.filter(recovery=True)], [self.c02])

    def test_credential_on_the_system_page(self):
        page = lambda: self.client.get(f"/admin/systems/system/{self.system.pk}/change/").content.decode()  # noqa: E731
        self.assertIn("None: this system uses the shared API key.", page())
        credential, _ = issue_credential(self.ca, make_csr(), 30 * DAY, system=self.system)
        self.assertIn("days left); last used never.", page())
        credential.revoke()
        self.assertIn("Expired or revoked", page())


class FakeMPCC:
    """ The mPCC a node's renewal helper talks to. """

    def __init__(self, ca, renew_status=200, recover_status=200, challenge=True):
        self.ca, self.statuses = ca, {"renew": renew_status, "recover": recover_status}
        self.challenge = challenge
        self.posts = []

    def post(self, url, data, **kwargs):
        kind = url.rstrip("/").rsplit("/", 1)[-1]
        self.posts.append((kind, kwargs))
        status = self.statuses[kind]
        if isinstance(status, Exception):
            raise status
        if status != 200:
            reply = Reply(status, "no")
            reply.headers = {"WWW-Authenticate": 'TLS-Client-Certificate realm="mprov"'} \
                if status == 401 and self.challenge else {}
            return reply
        cert = self.ca.sign_csr(check_csr(json.loads(data)["csr"]), "mprov.sys.1", "system", 30 * DAY)
        return Reply(200, body={"certificate": cert_pem(cert)})


class RenewalHelperTests(SimpleTestCase):
    """ #506: mprov_enroll.py renew/recover/status, which images run at boot
    and daily. """

    def setUp(self):
        self.m = load_enroll_module()
        self.ca = CA.create("test CA")
        self.tls = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self.tls, True)
        # never the real /tmp/mprov_enroll_spent
        spent_dir = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, spent_dir, True)
        self.m.SPENT = os.path.join(spent_dir, "spent")
        self.log = []

    def credential(self, lifetime):
        """ A node credential in self.tls valid for lifetime (negative: expired). """
        key_path = os.path.join(self.tls, "node.key")
        csr = check_csr(self.m.make_csr(key_path))
        if lifetime < datetime.timedelta(0):
            # signed in the past, so it has already expired
            cert = self.ca.sign_csr(csr, "mprov.sys.1", "system", 30 * DAY,
                                    now=datetime.datetime.now(datetime.timezone.utc) - 30 * DAY + lifetime)
        else:
            cert = self.ca.sign_csr(csr, "mprov.sys.1", "system", lifetime)
        for name, text in (("node.crt", cert_pem(cert)), ("ca.crt", cert_pem(self.ca.cert)),
                           ("mpcc_url", "https://10.0.0.1/\n")):
            with open(os.path.join(self.tls, name), "w") as f:
                f.write(text)
        return cert

    def renew(self, session):
        return self.m.renew(session, tls_dir=self.tls, log=self.log.append)

    def serial(self):
        from cryptography import x509
        with open(os.path.join(self.tls, "node.crt"), "rb") as f:
            return x509.load_pem_x509_certificate(f.read()).serial_number

    def test_nothing_to_renew(self):
        self.assertTrue(self.renew(FakeMPCC(self.ca)))
        self.assertIn("uses the shared API key", self.log[-1])

    def test_not_due(self):
        # the mPCC is asked, and says so (#532)
        old = self.credential(30 * DAY).serial_number
        session = FakeMPCC(self.ca, renew_status=409)
        self.assertTrue(self.renew(session))
        self.assertEqual([kind for kind, _ in session.posts], ["renew"])
        self.assertEqual(self.log, ["The credential isn't due for renewal."])
        self.assertEqual(self.serial(), old)

    def test_a_revoked_credential_reenrolls_through_the_window(self):
        # #532: in date, but the mPCC refuses it; an admin opened a window
        old = self.credential(30 * DAY).serial_number
        session = FakeMPCC(self.ca, renew_status=401)
        self.assertTrue(self.renew(session))
        self.assertEqual([kind for kind, _ in session.posts], ["renew", "recover"])
        self.assertNotIn("cert", session.posts[1][1])
        self.assertNotEqual(self.serial(), old)
        self.assertIn("refused this node's certificate", self.log[0])
        self.assertEqual(self.log[-1], "Re-enrolled; the credential is current again.")

    def test_a_revoked_credential_without_a_window_says_what_to_do(self):
        old = self.credential(30 * DAY).serial_number
        self.assertFalse(self.renew(FakeMPCC(self.ca, renew_status=401, recover_status=403)))
        self.assertEqual(self.serial(), old)
        self.assertIn("The mPCC refused this node's certificate. In the mPCC", self.log[-1])
        self.assertIn("Let these systems re-enroll", self.log[-1])

    def test_a_401_without_the_certificate_challenge_isnt_a_revocation(self):
        # e.g. a proxy in the way: not the mPCC refusing the certificate
        self.credential(30 * DAY)
        session = FakeMPCC(self.ca, renew_status=401, challenge=False)
        self.assertTrue(self.renew(session))
        self.assertEqual([kind for kind, _ in session.posts], ["renew"])
        self.assertIn("Warning: couldn't check the credential", self.log[-1])

    def test_an_unreachable_mpcc_isnt_an_error_until_its_due(self):
        self.credential(30 * DAY)
        session = FakeMPCC(self.ca, renew_status=OSError("no route to host"))
        self.assertTrue(self.renew(session))
        self.assertEqual([kind for kind, _ in session.posts], ["renew"])
        self.assertIn("couldn't renew (OSError", self.log[0])
        self.assertIn("checked again next time", self.log[-1])

    def test_an_unreachable_mpcc_when_due_tries_recovery(self):
        self.credential(10 * DAY)
        session = FakeMPCC(self.ca, renew_status=OSError("no route to host"), recover_status=OSError("no route"))
        self.assertFalse(self.renew(session))
        self.assertEqual([kind for kind, _ in session.posts], ["renew", "recover"])
        self.assertIn("The credential has expired or is about to.", self.log[-1])

    def test_renews_in_its_window(self):
        old = self.credential(10 * DAY).serial_number
        session = FakeMPCC(self.ca)
        self.assertTrue(self.renew(session))
        kind, kwargs = session.posts[0]
        self.assertEqual(kind, "renew")
        self.assertEqual(kwargs["cert"], (os.path.join(self.tls, "node.crt"), os.path.join(self.tls, "node.key")))
        self.assertTrue(kwargs["verify"].endswith("ca.crt"))
        self.assertNotEqual(self.serial(), old)
        self.assertTrue(self.m.valid_for(20 * 86400, self.tls))
        self.assertEqual(sorted(os.listdir(self.tls)), ["ca.crt", "mpcc_url", "node.crt", "node.key"])

    def test_expired_goes_straight_to_recovery(self):
        self.credential(-DAY)
        session = FakeMPCC(self.ca)
        self.assertTrue(self.renew(session))
        kind, kwargs = session.posts[0]
        self.assertEqual(kind, "recover")
        self.assertNotIn("cert", kwargs)
        self.assertTrue(self.m.valid_for(20 * 86400, self.tls))

    def test_a_refused_renewal_tries_recovery(self):
        self.credential(10 * DAY)
        session = FakeMPCC(self.ca, renew_status=403)
        self.assertTrue(self.renew(session))
        self.assertEqual([kind for kind, _ in session.posts], ["renew", "recover"])

    def test_no_window_keeps_the_old_credential_and_says_what_to_do(self):
        old = self.credential(-DAY).serial_number
        self.assertFalse(self.renew(FakeMPCC(self.ca, recover_status=403)))
        self.assertEqual(self.serial(), old)
        self.assertIn("Let these systems re-enroll", self.log[-1])
        self.assertEqual(sorted(os.listdir(self.tls)), ["ca.crt", "mpcc_url", "node.crt", "node.key"])

    def test_status_and_command_line(self):
        self.credential(10 * DAY)
        self.assertTrue(self.m.status(self.tls, log=self.log.append))
        self.assertIn("mprov.sys.1", self.log[0])
        self.assertEqual(self.log[-1], "valid")
        self.assertEqual(self.m.main(["nope"]), 2)

    def test_enroll_records_the_mpccs_address(self):
        from pki.test_node_enroll import FakeSession
        from pki.ca import fingerprint
        cmdline = os.path.join(self.tls, "cmdline")
        with open(cmdline, "w") as f:
            f.write(f"mprov_enroll={'a' * 32} mprov_ca={fingerprint(self.ca.cert)}\n")
        tls = os.path.join(self.tls, "tls")
        self.assertTrue(self.m.enroll(FakeSession(self.ca), "http://10.0.0.1/", cmdline=cmdline, tls_dir=tls,
                                      log=self.log.append))
        with open(os.path.join(tls, "mpcc_url")) as f:
            self.assertEqual(f.read(), "https://10.0.0.1/\n")

