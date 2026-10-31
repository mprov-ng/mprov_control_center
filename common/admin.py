
from copy import deepcopy
from django.contrib import admin
from django import forms
from django.core.exceptions import ImproperlyConfigured
from django.forms.fields import IntegerField, Field, HiddenInput
from django.forms import Media


# wizard on first step has 'wizard_step' unset
# subsequent steps must include it in 
# the form. should be able to add the field programmatically

class AdminWizardModel(admin.ModelAdmin):
  # A ModelAdmin instance is shared by every request, so the wizard's step,
  # inlines and readonly fields are worked out per request, never stored on
  # self: two people adding at once must not see each other's step (#270).
  step_fields = None
  extra_js = []
  appname = ""

  def __init__(self, model, admin_site):
    self.base_readonly_fields = deepcopy(self.readonly_fields)
    self.appname = model._meta.app_label
    
    super().__init__(model, admin_site)

  def wizard_step(self, request):
    """ This request's step: the POSTed wizard_step, or 0 for anything
    else.  Kept on the request, which only this request sees. """
    if not hasattr(request, '_mprov_wizard_step'):
      step = 0
      if request.method == 'POST':
        try:
          step = max(int(request.POST.get('wizard_step', 0)), 0)
        except (TypeError, ValueError):
          step = 0
      request._mprov_wizard_step = step
    return request._mprov_wizard_step

  def adding_in_wizard(self, obj):
    """ An add form of a wizard: it has no inlines or readonly fields. """
    return obj is None and self.step_fields is not None

  def get_inlines(self, request, obj):
    if self.adding_in_wizard(obj):
      return []
    return super().get_inlines(request, obj)

  def get_readonly_fields(self, request, obj=None):
    if self.adding_in_wizard(obj):
      return []
    return super().get_readonly_fields(request, obj)
  
  @property
  def media(self) -> Media:
    media = super().media
    
    media_js = []
    for url in self.extra_js:

      media_js.append(f"{self.appname}/admin/js/{url}")
  
    extra_media = Media(js=media_js, css={'all': ("common/admin/css/wizard.css",)})
    
    media = media + extra_media
    return media

  def add_view(self, request, form_url='', extra_context=None):
    step = self.wizard_step(request)
    if self.step_fields is not None:
      if step >= len(self.step_fields):
        # we have gotten to the end of the wizard.
        # we are showing the whole form, let's give the user the 'Save & Edit' button
        extra_context = {
          'show_save_and_continue':True,
          'show_save_and_add_another':False,
          'show_save':False,
          'show_close':False,
          }
        return super().add_view(request, form_url, extra_context)
      
      if self.step_fields[step] is not None:
        extra_context = {
          'show_save_and_continue':False,
          'show_save_and_add_another':False,
          }
      else: 
        # we are showing the whole form, let's give the user the 'Save & Edit' button
        extra_context = {
          'show_save_and_continue':True,
          'show_save_and_add_another':False,
          'show_save':False,
          'show_close':False,
          }
    
    return super().add_view(request, form_url, extra_context)

  def get_form(self, request, obj=None, change=False, **kwargs):
    # special case for recursion, if we are getting the form for getting base fields.
    if 'getfields' in kwargs:
      kwargs.pop('getfields')
      return super().get_form(request, obj=obj, change=change, **kwargs)

    # in edit mode, or without step_fields, it's the normal form;
    # get_inlines() and get_readonly_fields() give the normal ones.
    if obj is not None or self.step_fields is None:
      return super().get_form(request, obj=obj, change=change, **kwargs)

    else:
      step = self.wizard_step(request)
      # if our current step is the end of the wizard, just display the form
      # as normal.
      if step >= len(self.step_fields):
        return super().get_form(request, obj=obj, change=change, **kwargs)


      # if step_fields is not a list, throw an exception
      if type(self.step_fields) is not list:
        raise ImproperlyConfigured("step_fields must be a list.")

      # # pass in the fields only for this step
      if step >= len(self.step_fields):
        kwargs['fields'] = None
      else: 
        kwargs['fields'] = self.step_fields[step]
      
      # grab the form instance and add our step to the form.
      form = super().get_form(request, obj=obj, change=change, **kwargs)


      if step+1 != len(self.step_fields):

        # DANGER WILL ROBINSON!  This is a nasty hack.
        if step > 0:
          request.POST._mutable = True
          request.POST.update({'wizard_step': step+1})
          request.POST._mutable = False

      form.base_fields['wizard_step'] = IntegerField(widget=HiddenInput(), initial=(step+1))

      # get another copy of the form to get the base fields.
      fform = self.get_form(request, obj, fields=None, getfields=True)
      dbfields = [*fform.base_fields, *self.get_readonly_fields(request, obj)]

      if step < len(self.step_fields):
        for field in self.base_readonly_fields:
          if self.step_fields[step] is None:
            if field in form.base_fields:
              form.base_fields[field].widget = forms.HiddenInput()
              
              if field in request.POST:
                form.base_fields[field].initial = request.POST.get(field)
          else:
            if field in dbfields and field not in self.step_fields[step]:
              if field not in form.base_fields:
                if field in request.POST:
                  form.base_fields[field] = Field(initial=request.POST.get(field), widget=HiddenInput())
              else:
                form.base_fields[field].widget = forms.HiddenInput()
                if field in request.POST:
                  form.base_fields[field].initial = request.POST.get(field)

      return form
      
