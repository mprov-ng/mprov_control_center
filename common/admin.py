
from copy import deepcopy
from django.contrib import admin
from django import forms
from django.core.exceptions import ImproperlyConfigured
from django.forms.fields import IntegerField, Field, HiddenInput
from django.forms import Media


# wizard on first step has 'wizard_step' unset
# subequent steps must include it in 
# the form. should be able to add field progammatically

class AdminWizardModel(admin.ModelAdmin):
  step_fields = None
  wizard_step = 0
  extra_js = []
  appname = ""

  def __init__(self, model, admin_site):
    self.base_readonly_fields = deepcopy(self.readonly_fields)
    self.base_inlines = deepcopy(self.inlines)
    self.inlines = []
    self.readonly_fields = []
    self.wizard_step = 0
    self.appname = model._meta.app_label
    
    super().__init__(model, admin_site)
  
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
    # if we were already submitted, get our new value for our current step  
    if 'wizard_step' in request.POST:
      self.wizard_step = int(request.POST.get('wizard_step'))
    else:
      self.wizard_step = 0

    if request.method != 'POST':
      self.wizard_step = 0
    
    if self.step_fields is not None:
      if self.wizard_step >= len(self.step_fields):
        # we have gotten to the end of the wizard.
        # we are showing the whole form, let's give the user teh Save and Edit button
        extra_context = {
          'show_save_and_continue':True,
          'show_save_and_add_another':False,
          'show_save':False,
          'show_close':False,
          }
        return super().add_view(request, form_url, extra_context)
      
      if self.step_fields[self.wizard_step] is not None:
        extra_context = {
          'show_save_and_continue':False,
          'show_save_and_add_another':False,
          }
      else: 
        # we are showing the whole form, let's give the user teh Save and Edit button
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

    # if an object is passed in, we are in edit mode.  Just send the form
    # as normal
    if obj is not None:
      self.readonly_fields=deepcopy(self.base_readonly_fields)
      self.inlines = deepcopy(self.base_inlines)
      form = super().get_form(request, obj=obj, change=change, **kwargs)
      return form
    
    # if step_fields is not set, don't act like a wizard.
    if self.step_fields == None:
      self.readonly_fields=deepcopy(self.base_readonly_fields)
      self.inlines = deepcopy(self.base_inlines)
      form = super().get_form(request, obj=obj, change=change, **kwargs)
      return form
    

    else:      
      # if our current step is the end of the wizard, just display the form
      # # as normal. 
      # # XXX: Should we change this?
      if self.wizard_step >= len(self.step_fields):
        return super().get_form(request, obj=obj, change=change, **kwargs)
      
      if self.wizard_step == 0:
        self.inlines = []
        self.readonly_fields = []
        

      # if step_fields is not a list, throw an exception
      if type(self.step_fields) is not list:
        raise ImproperlyConfigured("step_fields must be a list.")

      # # pass in the fields only for this step
      if self.wizard_step >= len(self.step_fields):
        kwargs['fields'] = None
      else: 
        kwargs['fields'] = self.step_fields[self.wizard_step]
      
      # grab the form instance and add our step to the form.
      form = super().get_form(request, obj=obj, change=change, **kwargs)


      if self.wizard_step+1 != len(self.step_fields):

        # DANGER WILL ROBINSON!  This is a nasty hack.
        if self.wizard_step > 0:
          request.POST._mutable = True
          request.POST.update({'wizard_step': self.wizard_step+1})
          request.POST._mutable = False

      form.base_fields['wizard_step'] = IntegerField(widget=HiddenInput(), initial=(self.wizard_step+1))

      # get another copy of the form to get the base fields.
      fform = self.get_form(request, obj, fields=None, getfields=True)
      dbfields = [*fform.base_fields, *self.get_readonly_fields(request, obj)]

      if self.wizard_step < len(self.step_fields):
        for field in self.base_readonly_fields:
          if self.step_fields[self.wizard_step] == None:
            if field in form.base_fields:
              form.base_fields[field].widget = forms.HiddenInput()
              
              if field in request.POST:
                form.base_fields[field].initial = request.POST.get(field)
          else:
            if field in dbfields and field not in self.step_fields[self.wizard_step]:
              if field not in form.base_fields:
                if field in request.POST:
                  form.base_fields[field] = Field(initial=request.POST.get(field), widget=HiddenInput())
              else:
                form.base_fields[field].widget = forms.HiddenInput()
                if field in request.POST:
                  form.base_fields[field].initial = request.POST.get(field)

      return form
      
