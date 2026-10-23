from django.forms import modelform_factory
from django.test import SimpleTestCase



class NetworkInterfaceInlineTests(SimpleTestCase):
  """ The NIC inline's IP Address box isn't narrowed, so it is as wide as the BMC inline's (#181). """

  def test_ipaddress_width_not_overridden(self):
    from systems.admin import NetForm
    from systems.models import NetworkInterface
    form = modelform_factory(NetworkInterface, form=NetForm, fields='__all__')
    self.assertNotIn('style', form.base_fields['ipaddress'].widget.attrs)
