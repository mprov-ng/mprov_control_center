from django.forms import ModelForm, PasswordInput
from .models import OSDistro

class OSDistro_form(ModelForm):
 
  class Meta:
    fields = "__all__"
    model = OSDistro
    widgets = {
      'rootpw': PasswordInput()
    }