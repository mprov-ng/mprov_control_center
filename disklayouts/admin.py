from django.contrib import admin
from disklayouts.models import DiskLayout, DiskPartition, RaidLayout
from common.admin import AdminWizardModel
from django import forms
from django.db.models import Q

class PartForm(forms.ModelForm):
    class Meta:
        widgets = {
            'partnum': forms.NumberInput(attrs={
              'style': 'width: 4em;',
              'class': 'vIntegerField',
              }),
            'size': forms.NumberInput(attrs={
              'style': 'width: 7em;',
              'class': 'vIntegerField',
            }),
            'filesystem': forms.TextInput(attrs={
              'size': '10',
              'class': 'vTextField',
            })
        }

class DiskPartitionInline(admin.TabularInline):
  form=PartForm
  model = DiskPartition
  extra = 1
  ordering = ['partnum']
  description = "When adding physical partitions that will be used as software RAID members, add the word 'raid' to mount point AND filesystem."
  

class DiskLayoutAdmin(AdminWizardModel):
  inlines = [DiskPartitionInline]
  step_fields = [['dtype'],None]
  readonly_fields = ['dtype', 'slug']
  list_fields = ['name', 'dtype', 'diskname']
  exclude=['slug']
  def get_queryset(self, request):
    qs = super(DiskLayoutAdmin, self).get_queryset(request)
    return qs.filter(~Q(dtype=DiskLayout.DiskTypes.MDRD))

  def get_form(self, request, obj=None, change=False, **kwargs):
    form = super().get_form(request, obj, change, **kwargs)
    if self.wizard_step == 0 and obj==None:
      # we are displaying the type form
      # Software RAID is done in a separate list.
      if ('mdrd', 'Software RAID') in form.base_fields['dtype'].choices:
        form.base_fields['dtype'].choices.remove(('mdrd', 'Software RAID'))
    return form


class RaidLayoutAdmin(AdminWizardModel):
  readonly_fields = ['dtype', 'slug']
  exclude=['slug']

  def get_form(self, request, obj=None, **kwargs):
    form = super().get_form(request, obj, **kwargs)
    form.base_fields['diskname'].label = "RAID Device"
    return form

admin.site.register(DiskLayout, DiskLayoutAdmin)
admin.site.register(RaidLayout, RaidLayoutAdmin)