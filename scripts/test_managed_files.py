import shutil
import tempfile

from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from common import flat_config, render_config
from pki.test_auth import AgentTestCase
from scripts.models import File, validate_dest_path, validate_mode, validate_owner
from scripts.templating import render
from systems.models import SystemGroup


class ManagedFilesTestCase(AgentTestCase):
    """ #519: files placed into images, from their distro, groups and the image. """

    def setUp(self):
        super().setUp()
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, True)
        overrides = override_settings(MEDIA_ROOT=media)
        overrides.enable()
        self.addCleanup(overrides.disable)
        self.image.osdistro.config_params = "ntp: 10.0.0.1\n"
        self.image.osdistro.save()

    def make(self, slug, content=b"hello\n", dest="", template=False, **fields):
        item = File(name=slug, slug=slug, dest_path=dest, template=template,
                    filename=SimpleUploadedFile(slug, content), **fields)
        item.save()
        return item

    def files(self, obj=None):
        return render_config(obj or self.image)


class ValidationTests(ManagedFilesTestCase):
    def test_destinations(self):
        for good in ("", "/etc/chrony.conf", "/opt/x/y.cfg"):
            validate_dest_path(good)
        for bad in ("etc/x", "/etc/../x", "/etc/x/", "/etc//x", "/", "/proc/x", "/sys", "/dev/null", "/run/x"):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                validate_dest_path(bad)

    def test_mode_and_owner(self):
        validate_mode("0644")
        validate_mode("755")
        for bad in ("", "8", "07777", "rwx"):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                validate_mode(bad)
        for good in ("root", "chrony", "1000", "svc-user"):
            validate_owner(good)
        for bad in ("", "a b", "x;rm", "-x"):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                validate_owner(bad)

    def test_setuid_needs_a_superuser(self):
        item = self.make("tool", dest="/usr/local/bin/tool")
        staff = User.objects.create_user("ops", "o@x", "pw", is_staff=True)
        staff.user_permissions.add(*Permission.objects.filter(codename__in=["change_file", "view_file"]))
        self.client.force_login(staff)
        response = self.call("PATCH", f"/files/{item.slug}/", {"mode": "4755"})
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("setuid", response.content.decode())
        self.client.force_login(self.admin)
        self.assertEqual(self.call("PATCH", f"/files/{item.slug}/", {"mode": "4755"}).status_code, 200)


class MergeTests(ManagedFilesTestCase):
    def test_union_of_the_image_layers(self):
        group = SystemGroup.objects.create(name="rack1")
        self.image.systemgroups.add(group)
        a = self.make("a", dest="/etc/a")
        b = self.make("b", dest="/etc/b")
        c = self.make("c", dest="/etc/c")
        self.make("download-only")
        self.image.osdistro.files.add(a)
        group.files.add(b, a)
        self.image.files.add(c, File.objects.get(slug="download-only"))
        rendered = self.files()
        self.assertEqual([e['item'].slug for e in rendered['files']], ["a", "b", "c"])
        self.assertEqual(len(rendered['files'][0]['sources']), 2)  # distro and group
        self.assertEqual(rendered['file_conflicts'], [])

    def test_the_later_layer_wins_a_destination(self):
        distro_one = self.make("distro-chrony", dest="/etc/chrony.conf")
        image_one = self.make("image-chrony", dest="/etc/chrony.conf")
        self.image.osdistro.files.add(distro_one)
        self.image.files.add(image_one)
        rendered = self.files()
        self.assertEqual([e['item'].slug for e in rendered['files']], ["image-chrony"])
        conflict = rendered['file_conflicts'][0]
        self.assertEqual((conflict['replaced'], conflict['by']), (distro_one, image_one))

    def test_what_the_job_server_sees(self):
        plain = self.make("motd", dest="/etc/motd")
        tpl = self.make("chrony", b"server {{ params.ntp }}\n", dest="/etc/chrony.conf", template=True,
                        group="chrony", mode="0640")
        self.image.files.add(plain, tpl)
        files = {f['slug']: f for f in flat_config(self.files())['files']}
        self.assertEqual(files['chrony']['url'], f"/systemimages/{self.image.slug}/files/chrony/")
        self.assertEqual((files['chrony']['group'], files['chrony']['mode']), ("chrony", "0640"))
        self.assertTrue(files['motd']['url'].startswith("/media/files/motd-v1"))
        response = self.call("GET", f"/systemimages/{self.image.slug}/", pem=self.js_pem, ip="10.0.0.5")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual({f['slug'] for f in response.json()['config']['files']}, {"motd", "chrony"})


class TemplateTests(ManagedFilesTestCase):
    def test_renders_with_params_image_and_distro(self):
        item = self.make("t", b"{{ params.ntp }} {{ image.slug }} {{ distro.version }}\n", dest="/etc/t", template=True)
        self.assertEqual(render(item, self.image), (b"10.0.0.1 compute 9\n", None))

    def test_errors(self):
        for content, expected in ((b"{{ params.nope }}", "UndefinedError"), (b"{% if %}", "TemplateSyntaxError"),
                                  (b"{{ ''.__class__.__mro__ }}", "SecurityError"), (b"\xff\xfe", "UTF-8")):
            with self.subTest(content=content):
                item = self.make(f"bad{len(content)}{expected[:3]}".lower(), content, dest="/etc/x", template=True)
                data, error = render(item, self.image)
                self.assertIsNone(data)
                self.assertIn(expected, error)

    def test_a_plain_file_is_copied_byte_for_byte(self):
        item = self.make("bin", b"\x00\x01{{ not a template }}", dest="/opt/bin")
        self.assertEqual(render(item, self.image)[0], b"\x00\x01{{ not a template }}")


class EndpointTests(ManagedFilesTestCase):
    def url(self, slug):
        return f"/systemimages/{self.image.slug}/files/{slug}/"

    def test_a_job_server_gets_the_rendered_copy(self):
        self.image.files.add(self.make("chrony", b"server {{ params.ntp }}\n", dest="/etc/chrony.conf", template=True))
        response = self.call("GET", self.url("chrony"), pem=self.js_pem, ip="10.0.0.5")
        self.assertEqual((response.status_code, response.content), (200, b"server 10.0.0.1\n"))
        self.assertEqual(response["X-mProv-File-Version"], "1")

    def test_errors(self):
        self.image.files.add(self.make("broken", b"{{ params.nope }}", dest="/etc/b", template=True))
        response = self.call("GET", self.url("broken"), pem=self.js_pem, ip="10.0.0.5")
        self.assertEqual(response.status_code, 422)
        self.assertIn("UndefinedError", response.json()["detail"])
        self.assertEqual(self.call("GET", self.url("nope"), pem=self.js_pem, ip="10.0.0.5").status_code, 404)

    def test_people_need_view_permissions(self):
        self.image.files.add(self.make("motd", dest="/etc/motd"))
        staff = User.objects.create_user("ops", "o@x", "pw", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.call("GET", self.url("motd")).status_code, 403)
        staff.user_permissions.add(*Permission.objects.filter(codename__in=["view_file", "view_systemimage"]))
        self.client.force_login(User.objects.get(pk=staff.pk))
        self.assertEqual(self.call("GET", self.url("motd")).status_code, 200)


class AdminTests(ManagedFilesTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)

    def test_a_changed_file_lists_the_images_to_rebuild(self):
        item = self.make("motd", dest="/etc/motd")
        self.image.osdistro.files.add(item)
        response = self.client.post(f"/admin/scripts/file/{item.slug}/change/", {
            "name": "motd", "version": 2, "dest_path": "/etc/motd", "owner": "root", "group": "root",
            "mode": "0644"}, follow=True)
        self.assertContains(response, "1 image uses the file motd and needs a rebuild")

    def test_the_form_warns_about_secrets(self):
        self.assertContains(self.client.get("/admin/scripts/file/add/"), "Never put passwords")

    def test_the_rendered_config_tab_shows_files_and_problems(self):
        self.image.osdistro.files.add(self.make("one", dest="/etc/x"))
        self.image.files.add(self.make("two", dest="/etc/x"), self.make("t", b"{{ nope }}", dest="/etc/t", template=True))
        from common.rendered_config import rendered_config_context
        context = rendered_config_context(self.image)
        self.assertEqual([f['dest_path'] for f in context['files']], ["/etc/t", "/etc/x"])
        self.assertTrue(any("replaces one" in w for w in context['file_warnings']))
        self.assertTrue(any("won't build" in w and "UndefinedError" in w for w in context['file_warnings']))
