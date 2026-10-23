from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from osmanagement.models import OSDistro
from systems.models import NetworkInterface, System, SystemImage


class NoAuthForgedXFFTests(TestCase):
    """
    The unauthenticated /ipxe/ and /images/ endpoints must identify the
    client by the actual socket peer address (REMOTE_ADDR).
    X-Forwarded-For is honored only when the connection provably arrives
    from a proxy listed in settings.TRUSTED_PROXIES (exact IPs or CIDRs);
    a forged header from any other peer must have no effect.
    """

    def setUp(self):
        self.user = User.objects.create(username="xff-test")
        # Two managed systems with distinguishable rendered configs, so a
        # test can tell whose iPXE script the endpoint served.
        self.victim = self.make_system("victim", "10.0.0.8", "VICTIMCMDLINE", "victim-image")
        self.attacker = self.make_system("attacker", "10.0.0.9", "ATTACKERCMDLINE", "attacker-image")

    def make_system(self, name, ip, cmdline, imagename):
        distro = OSDistro.objects.create(
            name=f"{name}-distro", vendor="test", version="9", baseurl="http://localhost/",
            install_kernel_cmdline=cmdline, initial_mods="e1000", prov_interface="eth0", tmpfs_root_size=8,
        )
        image = SystemImage.objects.create(name=imagename, created_by=self.user, osdistro=distro)
        system = System.objects.create(hostname=name, created_by=self.user, systemimage=image)
        NetworkInterface.objects.create(system=system, name="eth0", ipaddress=ip, bootable=True)
        return system

    def get_ipxe(self, remote_addr, xff=None):
        meta = {"REMOTE_ADDR": remote_addr}
        if xff is not None:
            meta["HTTP_X_FORWARDED_FOR"] = xff
        return self.client.get("/ipxe/", **meta)

    def test_socket_peer_identifies_client(self):
        """Sanity: the real peer address still selects the system."""
        content = self.get_ipxe("10.0.0.8").content.decode()
        self.assertIn("VICTIMCMDLINE", content)

    def test_forged_xff_from_untrusted_peer_is_ignored(self):
        """A forged X-Forwarded-For naming a managed IP must not fetch
        that system's iPXE config; the real peer (unmanaged, and with no
        __nads__ image configured) 404s instead."""
        response = self.get_ipxe("203.0.113.5", "10.0.0.8")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("VICTIMCMDLINE", response.content.decode())

    def test_forged_leftmost_chain_serves_the_real_peer(self):
        """Even behind a trusted proxy, a chain an attacker prepended to
        ("victim-ip, real-client-ip") must resolve to the real client —
        the trusted proxy appends on the right, so walk right to left."""
        with override_settings(TRUSTED_PROXIES=["203.0.113.0/24"]):
            content = self.get_ipxe("203.0.113.9", "10.0.0.8, 10.0.0.9").content.decode()
        self.assertIn("ATTACKERCMDLINE", content)
        self.assertNotIn("VICTIMCMDLINE", content)

    def test_xff_honored_from_configured_trusted_proxy(self):
        """A proxy listed in TRUSTED_PROXIES may identify the client."""
        with override_settings(TRUSTED_PROXIES=["203.0.113.1"]):
            content = self.get_ipxe("203.0.113.1", "10.0.0.8").content.decode()
        self.assertIn("VICTIMCMDLINE", content)


class ImagesAPIViewForgedXFFTests(TestCase):
    """
    /images/<pk>/ picks a job server the client can resolve; the address
    family used for that lookup must come from the socket peer, not from
    a spoofable header.
    """

    def setUp(self):
        from jobqueue.models import JobServer
        user = User.objects.create(username="xff-images-test")
        self.image = SystemImage.objects.create(name="xff-compute", created_by=user, needs_rebuild=False)
        self.js = JobServer.objects.create(name="js", address="js.example", one_minute_load=0.1)
        self.image.jobservers.add(self.js)
        self.families = []

        def resolve(name, rdtype, search=True):
            self.families.append(rdtype)
            return SimpleNamespace(rrset=["10.0.0.2"])

        for patcher in (
            mock.patch("systems.views_noauth.dns.resolver.resolve", side_effect=resolve),
            mock.patch("systems.views_noauth.requests.head", return_value=SimpleNamespace(status_code=200)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_forged_xff_cannot_switch_dns_lookup_family(self):
        """An IPv4 socket peer forging an IPv6 X-Forwarded-For must still
        get A-record job server lookups."""
        response = self.client.get(
            "/images/xff-compute/",
            REMOTE_ADDR="10.0.0.50", HTTP_X_FORWARDED_FOR="2001:db8::5",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(set(self.families), {"A"})

    def test_real_ipv6_peer_gets_aaaa_lookups(self):
        """Sanity: a genuine IPv6 peer still gets AAAA record lookups."""
        response = self.client.get("/images/xff-compute/", REMOTE_ADDR="2001:db8::5")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(set(self.families), {"AAAA"})
