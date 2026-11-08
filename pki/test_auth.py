import datetime
import json
import shutil
import tempfile
from urllib.parse import quote

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework_api_key.models import APIKey

from jobqueue.models import Job, JobModule, JobServer, JobStatus
from mprov_control_center.version import API_VERSION
from networks.models import Network, NetworkType
from osmanagement.models import OSDistro
from pki.ca import CA, check_csr, cert_pem
from pki.issue import issue_credential
from pki.models import AgentCredential
from pki.test_ca import make_csr
from systems.models import NetworkInterface, System, SystemBMC, SystemImage

DAY = datetime.timedelta(days=1)
DENIED = (401, 403)


class AgentTestCase(TestCase):
    """ Two systems, c01 (10.0.0.20) and c02 (10.0.0.21), each with a BMC,
    a job server, and this install's CA in a temporary MPROV_TLS_DIR. """

    def setUp(self):
        self.tls_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tls_dir, True)
        settings = override_settings(MPROV_TLS_DIR=self.tls_dir, MPROV_SKIP_VERSION_CHECK=False)
        settings.enable()
        self.addCleanup(settings.disable)
        self.ca = CA.create("test CA")
        self.ca.save(self.tls_dir)

        self.admin = User.objects.create_superuser("admin", "admin@example.com", "password")
        net_type = NetworkType.objects.create(name="Ethernet")
        self.lan = Network.objects.create(name="lan", net_type=net_type, subnet="10.0.0.0", netmask=24)
        self.other_net = Network.objects.create(name="other", net_type=net_type, subnet="10.1.0.0", netmask=24)
        distro = OSDistro.objects.create(name="d", vendor="v", version="9", baseurl="http://localhost/",
                                         install_kernel_cmdline="quiet", initial_mods="e1000",
                                         prov_interface="eth0", tmpfs_root_size=8)
        self.image = SystemImage.objects.create(name="compute", created_by=self.admin, osdistro=distro)
        self.c01 = System.objects.create(hostname="c01", created_by=self.admin, systemimage=self.image)
        self.c02 = System.objects.create(hostname="c02", created_by=self.admin, systemimage=self.image)
        self.nic1 = NetworkInterface.objects.create(system=self.c01, name="eth0", ipaddress="10.0.0.20",
                                                    network=self.lan, hostname="c01", bootable=True)
        self.nic2 = NetworkInterface.objects.create(system=self.c02, name="eth0", ipaddress="10.0.0.21",
                                                    network=self.lan, hostname="c02")
        self.bmc1 = SystemBMC.objects.create(system=self.c01, ipaddress="10.0.1.20", password="secret1",
                                             network=self.lan)
        self.bmc2 = SystemBMC.objects.create(system=self.c02, ipaddress="10.0.1.21", password="secret2",
                                             network=self.lan)
        self.js = JobServer.objects.create(name="js1", host_id="host-abc", address="10.0.0.5")
        self.js2 = JobServer.objects.create(name="js2", host_id="host-def", address="10.0.0.6")

        self.c01_cred, self.c01_pem = issue_credential(self.ca, make_csr(), DAY, system=self.c01)
        self.js_cred, self.js_pem = issue_credential(self.ca, make_csr(), DAY, jobserver=self.js)

    def call(self, method, url, body=None, pem=None, ip="10.0.0.20", version=API_VERSION, **extra):
        # CONTENT_TYPE as a header, so a GET gets JSON, not the docs page
        meta = {"REMOTE_ADDR": ip, "CONTENT_TYPE": "application/json", **extra}
        if pem is not None:
            meta.update(SSL_CLIENT_CERT=pem, SSL_CLIENT_VERIFY="SUCCESS")
        if version is not None:
            meta["HTTP_MPROV_VERSION"] = version
        kwargs = {}
        if body is not None:
            kwargs = {"data": json.dumps(body), "content_type": "application/json"}
        return getattr(self.client, method.lower())(url, **kwargs, **meta)

    def as_c01(self, method, url, body=None, **extra):
        return self.call(method, url, body, pem=self.c01_pem, **extra)

    def as_js(self, method, url, body=None, **extra):
        return self.call(method, url, body, pem=self.js_pem, ip="10.0.0.5", **extra)


class ClientCertAuthenticationTests(AgentTestCase):
    """ #381: a certificate from this CA, on record and in date, is the agent's identity. """

    def test_a_system_reads_itself(self):
        response = self.as_c01("GET", "/systems/?self")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([s["hostname"] for s in response.json()], ["c01"])

    def test_last_seen_is_recorded(self):
        self.assertIsNone(self.c01_cred.last_seen)
        self.as_c01("GET", "/systems/?self")
        self.assertIsNotNone(AgentCredential.objects.get(pk=self.c01_cred.pk).last_seen)

    def test_refused_certificates(self):
        other_ca = CA.create("other")
        foreign = cert_pem(other_ca.sign_csr(check_csr(make_csr()), "mprov.sys.1", "system", DAY))
        unknown = cert_pem(self.ca.sign_csr(check_csr(make_csr()), "mprov.sys.1", "system", DAY))
        revoked_cred, revoked = issue_credential(self.ca, make_csr(), DAY, system=self.c01)
        revoked_cred.revoke()
        expired_cred, expired = issue_credential(self.ca, make_csr(), DAY, system=self.c01)
        AgentCredential.objects.filter(pk=expired_cred.pk).update(not_after=timezone.now() - DAY)
        for name, pem in (("another CA", foreign), ("not on record", unknown), ("revoked", revoked),
                          ("expired", expired), ("garbage", "-----BEGIN CERTIFICATE-----\nAA\n-----END CERTIFICATE-----\n")):
            with self.subTest(name):
                self.assertEqual(self.call("GET", "/systems/?self", pem=pem).status_code, 401)

    def test_unverified_by_apache_is_refused(self):
        response = self.call("GET", "/systems/?self", SSL_CLIENT_CERT=self.c01_pem, SSL_CLIENT_VERIFY="FAILED:x")
        self.assertEqual(response.status_code, 401)

    def test_a_systems_certificate_from_another_address_is_refused(self):
        self.assertEqual(self.as_c01("GET", "/systems/?self", ip="10.0.0.21").status_code, 401)
        self.assertEqual(self.as_c01("GET", "/systems/?self", ip="192.0.2.9").status_code, 401)

    def test_a_disabled_service_user_is_refused(self):
        User.objects.filter(pk=self.c01_cred.user_id).update(is_active=False)
        self.assertEqual(self.as_c01("GET", "/systems/?self").status_code, 401)

    def test_no_ca_refuses_certificates(self):
        shutil.rmtree(self.tls_dir)
        self.assertEqual(self.as_c01("GET", "/systems/?self").status_code, 401)

    @override_settings(TRUSTED_PROXIES=["10.9.0.1"])
    def test_a_trusted_proxy_can_forward_it(self):
        header = {"HTTP_X_SSL_CLIENT_CERT": quote(self.c01_pem), "HTTP_X_FORWARDED_FOR": "10.0.0.20"}
        response = self.call("GET", "/systems/?self", ip="10.9.0.1", **header)
        self.assertEqual(response.status_code, 200, response.content)
        # from anyone else the header is ignored: no credentials at all
        self.assertIn(self.call("GET", "/systems/?self", ip="10.0.0.20", **header).status_code, DENIED)


class SystemRuleTests(AgentTestCase):
    """ #381: a system's certificate reaches only what the node scripts use, for itself. """

    def assertAllowed(self, method, url, body=None):
        response = self.as_c01(method, url, body)
        self.assertNotIn(response.status_code, DENIED, f"{method} {url}: {response.content[:300]}")
        return response

    def assertRefused(self, method, url, body=None):
        response = self.as_c01(method, url, body)
        self.assertEqual(response.status_code, 403, f"{method} {url}: {response.content[:300]}")

    def test_what_the_node_scripts_do(self):
        self.assertAllowed("GET", "/")
        self.assertAllowed("GET", "/systems/?self")
        self.assertAllowed("GET", "/systems/?hostname=c01")
        self.assertAllowed("GET", f"/networkinterfaces/?system={self.c01.pk}")
        self.assertAllowed("GET", "/networkinterfaces/?hostname=c01")
        self.assertAllowed("PATCH", f"/networkinterfaces/{self.nic1.pk}/", {"ipv6ll": "fe80::1"})
        self.assertAllowed("GET", f"/networks/{self.lan.pk}/")
        self.assertAllowed("GET", "/systembmcs/?self&detail")
        self.assertAllowed("GET", f"/systembmcs/?system={self.c01.pk}&detail")
        self.assertAllowed("PATCH", f"/systembmcs/{self.bmc1.pk}/", {"id": self.bmc1.pk, "mac": "aa:bb:cc:dd:ee:ff",
                                                                     "ipv6ll": "fe80::2"})
        self.assertAllowed("POST", "/systems/?self", {"booted": True})
        self.assertAllowed("POST", "/systems/?self", {"netboot": False})
        self.assertAllowed("POST", "/systems/?self", {"serial": "ABC123"})

    def test_its_own_bmc_password_only(self):
        detail = self.assertAllowed("GET", "/systembmcs/?self&detail").json()
        self.assertEqual([b["password"] for b in detail], ["secret1"])

    def test_nothing_of_another_systems(self):
        self.assertRefused("GET", f"/systems/{self.c02.pk}/")
        self.assertRefused("GET", "/systems/?hostname=c02")
        self.assertRefused("GET", f"/networkinterfaces/?system={self.c02.pk}")
        self.assertRefused("GET", "/networkinterfaces/?hostname=c02")
        self.assertRefused("GET", f"/networkinterfaces/{self.nic2.pk}/")
        self.assertRefused("PATCH", f"/networkinterfaces/{self.nic2.pk}/", {"ipv6ll": "fe80::1"})
        self.assertRefused("GET", f"/networks/{self.other_net.pk}/")
        self.assertRefused("GET", f"/systembmcs/?system={self.c02.pk}&detail")
        self.assertRefused("GET", f"/systembmcs/{self.bmc2.pk}/")
        self.assertRefused("PATCH", f"/systembmcs/{self.bmc2.pk}/", {"mac": "aa:bb:cc:dd:ee:ff"})

    def test_no_lists_or_other_endpoints(self):
        for url in ("/systems/", "/networkinterfaces/", "/systembmcs/", "/networks/", "/jobs/", "/jobservers/",
                    "/systemimages/", "/distros/", "/repos/", "/systems/?self&hostname=c02"):
            with self.subTest(url=url):
                self.assertRefused("GET", url)

    def test_only_the_fields_it_sets(self):
        self.assertRefused("POST", "/systems/?self", {"netboot": False, "hostname": "evil"})
        self.assertRefused("PATCH", f"/networkinterfaces/{self.nic1.pk}/", {"ipaddress": "10.0.0.99"})
        self.assertRefused("PATCH", f"/systembmcs/{self.bmc1.pk}/", {"password": "x"})
        self.assertRefused("PATCH", f"/systems/{self.c01.pk}/", {"provision": True})
        self.assertRefused("DELETE", f"/systems/{self.c01.pk}/")
        self.assertRefused("POST", "/systems/", {"hostname": "new"})

    def test_self_is_tied_to_the_certificate(self):
        # c02 also has c01's address, and the views' address lookup finds c02
        # first: ?self would act on c02, so c01's certificate is refused.
        NetworkInterface.objects.filter(pk=self.nic1.pk).update(ipaddress="10.0.0.30")
        NetworkInterface.objects.create(system=self.c02, name="eth1", ipaddress="10.0.0.20", network=self.lan)
        NetworkInterface.objects.create(system=self.c01, name="eth1", ipaddress="10.0.0.20", network=self.lan)
        self.assertRefused("POST", "/systems/?self", {"booted": True})
        self.assertIsNone(System.objects.get(pk=self.c02.pk).last_booted)


class JobServerRuleTests(AgentTestCase):
    """ #381: a job server reads the inventory and writes only its own state. """

    def setUp(self):
        super().setUp()
        for pk, name in ((1, "PENDING"), (2, "RUNNING"), (3, "ERROR"), (4, "COMPLETE")):
            JobStatus.objects.get_or_create(pk=pk, defaults={"name": name})
        self.module = JobModule.objects.create(slug="image-update", name="Image Update")
        self.pending = Job.objects.create(name="pending", module=self.module)
        self.mine = Job.objects.create(name="mine", module=self.module, status_id=2, jobserver=self.js)
        self.theirs = Job.objects.create(name="theirs", module=self.module, status_id=2, jobserver=self.js2)

    def assertAllowed(self, method, url, body=None):
        response = self.as_js(method, url, body)
        self.assertNotIn(response.status_code, DENIED, f"{method} {url}: {response.content[:300]}")
        return response

    def assertRefused(self, method, url, body=None):
        response = self.as_js(method, url, body)
        self.assertEqual(response.status_code, 403, f"{method} {url}: {response.content[:300]}")

    def test_reads_the_inventory(self):
        for url in ("/", "/systems/", f"/systembmcs/?network={self.lan.pk}&detail", "/networkinterfaces/",
                    "/networks/?isdhcp=True", "/systemimages/", "/systemgroups/", "/distros/", "/repos/",
                    "/jobs/?jobserver=1&status=2", "/jobservers/", "/switches/"):
            with self.subTest(url=url):
                self.assertAllowed("GET", url)

    def test_no_bmc_passwords(self):
        rows = self.assertAllowed("GET", f"/systembmcs/?network={self.lan.pk}&detail").json()
        self.assertIsInstance(rows, list, rows)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(not row.get("password") for row in rows))

    def test_its_own_registration_and_heartbeat(self):
        self.assertAllowed("POST", "/jobservers/", {"name": "js1", "host_id": "host-abc", "port": 8080})
        self.assertRefused("POST", "/jobservers/", {"name": "js2", "host_id": "host-def", "port": 8080})
        self.assertRefused("POST", "/jobservers/", {"name": "js1", "port": 8080})
        self.assertAllowed("POST", f"/jobservers/{self.js.pk}/heartbeat/", {"address": "10.0.0.5"})
        self.assertRefused("POST", f"/jobservers/{self.js2.pk}/heartbeat/", {"address": "10.0.0.6"})

    def test_jobs(self):
        self.assertAllowed("POST", f"/jobs/{self.pending.pk}/claim/", {"jobserver": self.js.pk})
        self.assertRefused("POST", f"/jobs/{self.pending.pk}/claim/", {"jobserver": self.js2.pk})
        self.assertAllowed("PATCH", f"/jobs/{self.mine.pk}/", {"id": self.mine.pk, "pk": "image-update",
                                                               "status": 4, "end_time": None,
                                                               "jobserver": self.js.pk})
        self.assertRefused("PATCH", f"/jobs/{self.theirs.pk}/", {"status": 3})
        self.assertRefused("PATCH", f"/jobs/{self.mine.pk}/", {"status": 4, "jobserver": self.js2.pk})
        self.assertRefused("PATCH", f"/jobs/{self.mine.pk}/", {"params": {}})
        self.assertRefused("DELETE", f"/jobs/{self.mine.pk}/")

    def test_hosts_images_and_repos_as_itself(self):
        url = f"/systemimages/{self.image.slug}/?addjs"
        self.assertAllowed("PATCH", url, {"slug": self.image.slug, "jobservers": [self.js.pk]})
        self.assertRefused("PATCH", url, {"slug": self.image.slug, "jobservers": [self.js2.pk]})
        self.assertRefused("PATCH", f"/systemimages/{self.image.slug}/", {"jobservers": [self.js.pk]})
        self.assertRefused("PATCH", url, {"slug": self.image.slug, "jobservers": [self.js.pk], "needs_rebuild": True})
        self.assertAllowed("POST", "/ostypes/", {"slug": "rhel", "name": "Yum/DNF Based Linux"})

    def test_no_other_writes(self):
        self.assertRefused("PATCH", f"/systems/{self.c01.pk}/", {"provision": True})
        self.assertRefused("POST", "/systems/", {"hostname": "new"})
        self.assertRefused("DELETE", f"/systemimages/{self.image.slug}/")
        self.assertRefused("PATCH", f"/systembmcs/{self.bmc1.pk}/", {"password": "x"})
        self.assertRefused("GET", "/power/on/?hostname=c01")
        self.assertRefused("POST", "/networks/", {"name": "evil"})


class SharedKeyModeTests(AgentTestCase):
    """ #381: MPROV_SHARED_KEY_MODE decides where the shared key is still accepted. """

    def setUp(self):
        super().setUp()
        _, self.key = APIKey.objects.create_key(name="shared")

    def with_key(self, method, url, body=None, ip="10.0.0.20"):
        return self.call(method, url, body, ip=ip, HTTP_AUTHORIZATION=f"Api-Key {self.key}")

    def test_the_default_is_off(self):
        # 0.7.0 refuses the shared key unless a site turns it back on.
        from django.conf import settings
        self.assertEqual(settings.MPROV_SHARED_KEY_MODE, "off")
        response = self.with_key("GET", "/systems/?self")
        self.assertEqual(response.status_code, 403)
        self.assertIn("MPROV_SHARED_KEY_MODE=off", response.json()["detail"])

    def test_all_is_as_before(self):
        with self.settings(MPROV_SHARED_KEY_MODE="all"):
            self.assertEqual(self.with_key("GET", "/systems/", ip="192.0.2.1").status_code, 200)
            self.assertNotIn(self.with_key("PATCH", f"/systems/{self.c02.pk}/", {"provision": True}).status_code,
                             DENIED)

    def test_nodes_allows_only_what_a_node_does_to_itself(self):
        with self.settings(MPROV_SHARED_KEY_MODE="nodes"):
            self.assertEqual(self.with_key("GET", "/systems/?self").status_code, 200)
            self.assertNotIn(self.with_key("POST", "/systems/?self", {"booted": True}).status_code, DENIED)
            self.assertEqual(self.with_key("GET", f"/networkinterfaces/?system={self.c02.pk}").status_code, 403)
            self.assertEqual(self.with_key("GET", "/systems/").status_code, 403)
            # not from a known system: nothing at all
            self.assertEqual(self.with_key("GET", "/systems/?self", ip="192.0.2.1").status_code, 403)
            self.assertEqual(self.with_key("POST", "/jobservers/", {"name": "x", "host_id": "x"},
                                           ip="192.0.2.1").status_code, 403)

    def test_off_refuses_it(self):
        for mode in ("off", "bogus"):
            with self.subTest(mode=mode), self.settings(MPROV_SHARED_KEY_MODE=mode):
                response = self.with_key("GET", "/systems/?self")
                self.assertEqual(response.status_code, 403)
                self.assertIn("MPROV_SHARED_KEY_MODE", response.json()["detail"])

    def test_a_logged_in_user_is_unaffected(self):
        self.client.force_login(self.admin)
        with self.settings(MPROV_SHARED_KEY_MODE="off"):
            self.assertEqual(self.client.get("/systems/", content_type="application/json").status_code, 200)


class VersionLockTests(AgentTestCase):
    """ #381: the version lock covers every agent-authenticated request, not just the shared key. """

    def test_a_certificate_without_the_version_is_426(self):
        self.assertEqual(self.call("GET", "/jobservers/", pem=self.js_pem, ip="10.0.0.5", version=None).status_code,
                         426)
        self.assertEqual(self.call("GET", "/jobservers/", pem=self.js_pem, ip="10.0.0.5", version="0.1").status_code,
                         426)

    def test_basic_auth_without_the_version_is_426(self):
        import base64
        basic = "Basic " + base64.b64encode(b"admin:password").decode()
        self.assertEqual(self.call("GET", "/systems/", version=None, HTTP_AUTHORIZATION=basic).status_code, 426)
        self.assertEqual(self.call("GET", "/systems/", HTTP_AUTHORIZATION=basic).status_code, 200)

    def test_node_script_exemptions_still_apply(self):
        self.assertEqual(self.as_c01("GET", "/systems/?self", version=None).status_code, 200)


class AttributionTests(AgentTestCase):
    """ #327, #331, #381: a save is attributed to the agent's service user. """

    def test_an_agents_save_is_its_own(self):
        self.as_js("PATCH", f"/systemimages/{self.image.slug}/?addjs", {"slug": self.image.slug,
                                                                        "jobservers": [self.js.pk]})
        # who saved it last; created_by stays its creator (#493).
        self.assertEqual(SystemImage.objects.get(pk=self.image.pk).updated_by.username, "mprov.js.host-abc")

    def test_the_shared_key_is_its_own_service_user(self):
        """ #5: the shared key's writes are mprov.shared-key's, not the first superuser's. """
        _, key = APIKey.objects.create_key(name="shared")
        with self.settings(MPROV_SHARED_KEY_MODE="all"):
            response = self.call("PATCH", f"/systems/{self.c02.pk}/", {"hostname": "c02b"},
                                 HTTP_AUTHORIZATION=f"Api-Key {key}")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(System.objects.get(pk=self.c02.pk).updated_by.username, "mprov.shared-key")
