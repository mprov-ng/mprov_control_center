""" The API Tokens admin (#502): every staff user makes, lists and revokes
their own tokens; superusers see and revoke everyone's. """
from django import forms
from django.contrib import admin, messages
from django.utils.html import escape, mark_safe

from authcustom.models import UserToken


class UserTokenForm(forms.ModelForm):
  """ Making a token: a name, and optionally how long it lasts. """
  days = forms.IntegerField(min_value=1, max_value=3650, required=False,
                            help_text="Days until it expires. Leave empty for a token that doesn't expire.")

  class Meta:
    model = UserToken
    fields = ('name',)


@admin.register(UserToken)
class UserTokenAdmin(admin.ModelAdmin):
  list_display = ('name', 'prefix', 'user', 'created', 'expiry_date', 'last_used', 'revoked')
  list_filter = ('revoked',)
  search_fields = ('name', 'prefix', 'user__username')
  actions = ['revoke']

  def mine(self, request):
    return request.user.is_active and request.user.is_staff

  # every staff user manages their own tokens, without model permissions
  def has_module_permission(self, request):
    return self.mine(request)

  def has_view_permission(self, request, obj=None):
    return self.mine(request) and (obj is None or obj.user == request.user or request.user.is_superuser)

  def has_add_permission(self, request):
    return self.mine(request)

  def has_change_permission(self, request, obj=None):
    # nothing to edit after it's made; revoke with the action
    return False

  def has_delete_permission(self, request, obj=None):
    return self.has_view_permission(request, obj)

  def get_queryset(self, request):
    tokens = super().get_queryset(request).select_related('user')
    return tokens if request.user.is_superuser else tokens.filter(user=request.user)

  def get_form(self, request, obj=None, **kwargs):
    if obj is None:
      kwargs['form'] = UserTokenForm
    return super().get_form(request, obj, **kwargs)

  def get_fields(self, request, obj=None):
    if obj is None:
      return ('name', 'days')
    return ('name', 'prefix', 'user', 'created', 'expiry_date', 'last_used', 'revoked')

  def get_readonly_fields(self, request, obj=None):
    return () if obj is None else self.get_fields(request, obj)

  def save_model(self, request, obj, form, change):
    if change:
      return
    token, secret = UserToken.make(request.user, form.cleaned_data['name'], form.cleaned_data.get('days'))
    obj.pk = token.pk
    obj.refresh_from_db()
    self.message_user(request, mark_safe(
      f"Your API token, shown only this once: <code>{escape(secret)}</code><br>"
      "Use it as <code>Authorization: Token &lt;token&gt;</code>, or with mash: "
      "<code>connect &lt;url&gt; token &lt;token&gt;</code>. It acts as you, with your permissions."),
      messages.WARNING)

  @admin.action(description="Revoke selected tokens")
  def revoke(self, request, queryset):
    count = 0
    for token in self.get_queryset(request).filter(pk__in=queryset.values('pk'), revoked=False):
      token.revoked = True
      token.save(update_fields=['revoked'])
      count += 1
    self.message_user(request, f"Revoked {count} token" + ("" if count == 1 else "s") + ".")
