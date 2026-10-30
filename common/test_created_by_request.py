import base64
import json

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase

from rest_framework_api_key.models import APIKey

from networks.models import Switch
from systems.models import System, SystemImage


class CreatedByRequestTests(TestCase):
    """Items 5-8 via Django test client (exercises MIDDLEWARE order) for System, SystemImage, Switch."""

    def setUp(self):
        # pk=1 is the AnonymousUser mapping; keep it distinct from actor users.
        self.anon_target = User.objects.create_superuser("anon_target", "anon@example.com", "password")
        assert self.anon_target.pk == 1, f"expected pk=1, got {self.anon_target.pk}"
        self.staff = User.objects.create_superuser("staff", "staff@example.com", "password")
        self.basic_user = User.objects.create_user("basicuser", "basic@example.com", "password")
        _, self.api_key = APIKey.objects.create_key(name="jobserver-key")
        self.systems = 0
        self.images = 0
        self.switches = 0

    def _post_json(self, url, data, **extra):
        return self.client.post(url, json.dumps(data), content_type="application/json", **extra)

    def _patch_json(self, url, data, **extra):
        return self.client.patch(url, json.dumps(data), content_type="application/json", **extra)

    def _basic_auth_header(self, username, password):
        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        return f"Basic {token}"

    # Helpers that create each model with minimal required fields via the API

    def _create_system_via_api(self, hostname=None, **extra):
        self.systems += 1
        hostname = hostname or f"node-{self.systems}"
        # SystemSerializer requires created_by at validation time; signal overwrites it to the request user.
        # Send a valid dummy id (anon_target) so validation passes but overwrite is observable via expected value.
        dummy_created_by = extra.pop("dummy_created_by", self.anon_target.pk)
        resp = self._post_json("/systems/", {"hostname": hostname, "created_by": dummy_created_by}, **extra)
        self.assertEqual(resp.status_code, 201, resp.content)
        return System.objects.get(hostname=hostname)

    def _create_switch_via_api(self, hostname=None, **extra):
        self.switches += 1
        hostname = hostname or f"sw-{self.switches}"
        resp = self._post_json("/switches/", {"hostname": hostname, "mgmt_ip": f"10.0.0.{100+self.switches}", "mgmt_mac": f"de:ad:be:ef:00:{self.switches:02x}"}, **extra)
        self.assertEqual(resp.status_code, 201, resp.content)
        return Switch.objects.get(hostname=hostname)

    def _create_systemimage_via_api(self, name=None, **extra):
        self.images += 1
        name = name or f"img-{self.images}"
        dummy_created_by = extra.pop("dummy_created_by", self.anon_target.pk)
        resp = self._post_json("/systemimages/", {"name": name, "created_by": dummy_created_by, "jobservers": []}, **extra)
        self.assertEqual(resp.status_code, 201, resp.content)
        return SystemImage.objects.get(name=name)

    # 5: API-key request -> created_by pk=1

    def test_api_key_sets_created_by_to_pk1_system(self):
        # Item 5 System
        obj = self._create_system_via_api(HTTP_AUTHORIZATION=f"Api-Key {self.api_key}", dummy_created_by=self.staff.pk)
        self.assertEqual(obj.created_by_id, 1)

    def test_api_key_sets_created_by_to_pk1_switch(self):
        obj = self._create_switch_via_api(HTTP_AUTHORIZATION=f"Api-Key {self.api_key}")
        self.assertEqual(obj.created_by_id, 1)

    def test_api_key_sets_created_by_to_pk1_systemimage(self):
        obj = self._create_systemimage_via_api(HTTP_AUTHORIZATION=f"Api-Key {self.api_key}", dummy_created_by=self.staff.pk)
        self.assertEqual(obj.created_by_id, 1)

    # 6: logged-in staff via session auth (admin/API) -> created_by is that user

    def test_session_auth_sets_created_by_to_staff_system(self):
        self.client.force_login(self.staff)
        obj = self._create_system_via_api(dummy_created_by=self.anon_target.pk)
        self.assertEqual(obj.created_by, self.staff)

    def test_session_auth_sets_created_by_to_staff_switch(self):
        self.client.force_login(self.staff)
        obj = self._create_switch_via_api()
        self.assertEqual(obj.created_by, self.staff)

    def test_session_auth_sets_created_by_to_staff_systemimage(self):
        self.client.force_login(self.staff)
        obj = self._create_systemimage_via_api(dummy_created_by=self.anon_target.pk)
        self.assertEqual(obj.created_by, self.staff)

    def test_session_auth_patch_keeps_created_by_as_actor(self):
        """Item 6 also covers change: PATCH updates created_by to the actor."""
        self.client.force_login(self.staff)
        sys = self._create_system_via_api(hostname="change-me", dummy_created_by=self.anon_target.pk)
        # Patch via same staff user; signal should overwrite created_by to staff (already staff).
        # Now create a second actor and patch.
        other = User.objects.create_user("other", "other@example.com", "password")
        # Need staff perms? MProvView permission is HasAPIKeyOrIsAuthenticated, any authenticated user can write.
        self.client.force_login(other)
        resp = self._patch_json(f"/systems/{sys.id}/", {"hostname": "change-me-2"})
        self.assertEqual(resp.status_code, 200, resp.content)
        sys.refresh_from_db()
        self.assertEqual(sys.created_by, other)

    # 7: HTTP Basic auth on API -> created_by is Basic user, not pk=1

    def test_basic_auth_sets_created_by_to_basic_user_system(self):
        hdr = self._basic_auth_header("basicuser", "password")
        obj = self._create_system_via_api(HTTP_AUTHORIZATION=hdr, dummy_created_by=self.anon_target.pk)
        self.assertEqual(obj.created_by, self.basic_user)

    def test_basic_auth_sets_created_by_to_basic_user_switch(self):
        hdr = self._basic_auth_header("basicuser", "password")
        obj = self._create_switch_via_api(HTTP_AUTHORIZATION=hdr)
        self.assertEqual(obj.created_by, self.basic_user)

    def test_basic_auth_sets_created_by_to_basic_user_systemimage(self):
        hdr = self._basic_auth_header("basicuser", "password")
        obj = self._create_systemimage_via_api(HTTP_AUTHORIZATION=hdr, dummy_created_by=self.anon_target.pk)
        self.assertEqual(obj.created_by, self.basic_user)

    # 8: no request path

    def test_no_request_update_keeps_created_by(self):
        """Item 8: ORM save outside request keeps previous created_by."""
        sys = System.objects.create(hostname="keep-me", created_by=self.staff)
        sys.hostname = "keep-me-2"
        sys.save()
        sys.refresh_from_db()
        self.assertEqual(sys.created_by, self.staff)

    def test_no_request_create_without_created_by_raises(self):
        """Item 8: create without created_by still raises IntegrityError when no request."""
        # System has no DB default for created_by; signal is no-op when request is None,
        # so DB constraint should fire.
        with self.assertRaises(IntegrityError):
            System.objects.create(hostname="no-creator")

    def test_no_request_create_switch_without_created_by_raises(self):
        with self.assertRaises(IntegrityError):
            Switch.objects.create(hostname="sw-no-creator", mgmt_ip="10.0.0.99", mgmt_mac="de:ad:be:ef:00:99")

    def test_no_request_create_systemimage_without_created_by_raises(self):
        with self.assertRaises(IntegrityError):
            SystemImage.objects.create(name="img-no-creator")
