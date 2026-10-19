from django.test import SimpleTestCase

from systems.models import System


class BMCInlineTests(SimpleTestCase):
  """ The BMC inline is labelled "System BMC", with plural "System BMCs". """

  def test_labels(self):
    from systems.admin import BMCInline
    self.assertEqual(BMCInline.verbose_name, "System BMC")
    self.assertEqual(BMCInline.verbose_name_plural, "System BMCs")
