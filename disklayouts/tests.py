from django.contrib.auth.models import User
from django.test import TestCase

from disklayouts.models import DiskLayout


class DiskLayoutAdminTests(TestCase):
  """ The disk layout changelist shows the name, disk type and disk device. """

  def test_changelist_columns(self):
    user = User.objects.create_superuser("admin", "admin@example.com", "password")
    self.client.force_login(user)
    DiskLayout.objects.create(name="root disk", diskname="/dev/sda", slug="root-disk", dtype=DiskLayout.DiskTypes.SCSI)
    response = self.client.get("/admin/disklayouts/disklayout/")
    self.assertEqual(response.status_code, 200)
    content = response.content.decode()
    self.assertIn("field-dtype", content)
    self.assertIn("/dev/sda", content)
