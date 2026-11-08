import base64
import json

from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory, TestCase, override_settings
from rest_framework_api_key.models import APIKey

from common.request import NADS_USER, SHARED_KEY_USER, acting_user
from jobqueue.models import JobServer
from mprov_control_center.version import API_VERSION
from systems.models import NetworkInterface, System, SystemBMC, SystemGroup


@override_settings(MPROV_SKIP_VERSION_CHECK=False)
class APIHistoryTests(TestCase):
    """ #5: API writes go in the Admin Site History. """

    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "a@example.com", "pw")
        self.node = System.objects.create(hostname="c01", created_by=self.admin)
        self.nic = NetworkInterface.objects.create(system=self.node, name="eth0", ipaddress="10.0.0.11")
        self.auth = "Basic " + base64.b64encode(b"admin:pw").decode()

    def call(self, method, url, body=None, auth=None, **extra):
        kwargs = {"HTTP_AUTHORIZATION": auth or self.auth, "HTTP_MPROV_VERSION": API_VERSION, **extra}
        return getattr(self.client, method.lower())(url, json.dumps(body) if body is not None else None,
                                                    content_type="application/json", **kwargs)

    def entries(self, obj):
        return list(LogEntry.objects.filter(content_type=ContentType.objects.get_for_model(type(obj)),
                                            object_id=str(obj.pk)).order_by("pk"))

    def test_create_change_delete(self):
        response = self.call("POST", "/systemgroups/", {"name": "rack1"})
        self.assertEqual(response.status_code, 201, response.content)
        group = SystemGroup.objects.get(name="rack1")
        self.call("PATCH", f"/systemgroups/{group.pk}/", {"name": "rack2"})
        added, changed = self.entries(group)
        self.assertEqual((added.action_flag, added.user), (ADDITION, self.admin))
        self.assertEqual(changed.action_flag, CHANGE)
        self.assertEqual(changed.get_change_message(), "Changed Name.")
        self.assertEqual(changed.object_repr, str(SystemGroup.objects.get(pk=group.pk)))
        self.call("DELETE", f"/systemgroups/{group.pk}/")
        self.assertEqual(self.entries(group)[-1].action_flag, DELETION)

    def test_a_change_that_changes_nothing_isnt_recorded(self):
        self.call("PATCH", f"/systems/{self.node.pk}/", {"hostname": "c01"})
        self.assertEqual(self.entries(self.node), [])

    def test_names_fields_never_values(self):
        bmc = SystemBMC.objects.create(system=self.node, ipaddress="10.1.0.11", username="u", password="old-secret")
        self.call("PATCH", f"/systembmcs/{bmc.pk}/", {"password": "new-secret"})
        entry = self.entries(bmc)[-1]
        self.assertIn("Password", entry.get_change_message())
        self.assertNotIn("secret", entry.change_message)

    def test_job_queue_isnt_recorded(self):
        js = JobServer.objects.create(name="js1", host_id="h1")
        self.call("PATCH", f"/jobservers/{js.pk}/", {"name": "js2"})
        self.assertEqual(self.entries(js), [])

    def test_the_shared_key_is_its_own_user(self):
        _, key = APIKey.objects.create_key(name="shared")
        self.call("POST", "/systemgroups/", {"name": "rack9"}, auth=f"Api-Key {key}")
        group = SystemGroup.objects.get(name="rack9")
        entry = self.entries(group)[0]
        self.assertEqual(entry.user.username, SHARED_KEY_USER)
        self.assertFalse(entry.user.is_staff or entry.user.has_usable_password())
        # and created_by/updated_by follow (#493)
        response = self.call("POST", "/systems/", {"hostname": "c02", "created_by": self.admin.pk},
                             auth=f"Api-Key {key}")
        self.assertEqual(response.status_code, 201, response.content)
        system = System.objects.get(hostname="c02")
        self.assertEqual((system.created_by.username, system.updated_by.username), (SHARED_KEY_USER, SHARED_KEY_USER))

    def test_a_nodes_boot_report(self):
        """ Every boot is recorded, as the node's own credential's user when it
        has one; here the shared key. """
        _, key = APIKey.objects.create_key(name="shared")
        System.objects.filter(pk=self.node.pk).update(provision=True)
        for body in ({"netboot": False}, {"booted": True}, {"booted": True}):
            response = self.call("POST", "/systems/?self", body, auth=f"Api-Key {key}", REMOTE_ADDR="10.0.0.11")
            self.assertEqual(response.status_code, 200, response.content)
        messages = [e.get_change_message() for e in self.entries(self.node)]
        self.assertEqual(messages, ["Changed Provision?.", "Changed Last Booted.", "Changed Last Booted."])
        self.assertTrue(all(e.user.username == SHARED_KEY_USER for e in self.entries(self.node)))

    def test_nads_registration_is_its_own_user(self):
        """ #5: N.A.D.S. registration acts as mprov.nads; any other
        unauthenticated request still falls back to the first superuser. """
        from django.contrib.auth.models import AnonymousUser
        factory = RequestFactory()
        for path, expected in (("/systems/register", NADS_USER), ("/systems/register/", NADS_USER),
                               ("/ipxe/", "admin")):
            request = factory.post(path)
            request.user = AnonymousUser()
            with self.subTest(path=path):
                user = acting_user(request)
                self.assertEqual(user.username, expected)
        nads = User.objects.get(username=NADS_USER)
        self.assertFalse(nads.is_staff or nads.is_superuser or nads.has_usable_password())
