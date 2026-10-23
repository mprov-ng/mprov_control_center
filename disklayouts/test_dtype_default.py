from common.testing import APITestCase
from disklayouts.models import DiskLayout, RaidLayout


class DtypeDefaultTests(APITestCase):
  """ New disk layouts default to SCSI, and new RAID layouts to Software RAID (#271). """

  def test_disklayout_defaults_to_scsi(self):
    self.assertEqual(DiskLayout().dtype, DiskLayout.DiskTypes.SCSI)
    self.assertEqual(DiskLayout._meta.get_field('dtype').default, DiskLayout.DiskTypes.SCSI)

  def test_raidlayout_defaults_to_software_raid(self):
    raid = RaidLayout.objects.create(name="md0", diskname="/dev/md0", mount="/")
    self.assertEqual(raid.dtype, DiskLayout.DiskTypes.MDRD)
    self.assertEqual(RaidLayout.objects.get(pk=raid.pk).dtype, DiskLayout.DiskTypes.MDRD)

  def test_disklayout_without_dtype_stays_in_admin_list(self):
    DiskLayout.objects.create(name="root disk", diskname="/dev/sda")
    response = self.client.get("/admin/disklayouts/disklayout/")
    self.assertContains(response, "root disk")

  def test_saved_dtype_is_kept(self):
    DiskLayout.objects.create(name="nvme disk", diskname="/dev/nvme0n1", dtype=DiskLayout.DiskTypes.NVME)
    self.assertEqual(DiskLayout.objects.get(pk="nvme-disk").dtype, DiskLayout.DiskTypes.NVME)
