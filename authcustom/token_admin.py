""" The API Tokens admin (#502): every staff user makes, lists and revokes
their own tokens; superusers see and revoke everyone's.

On top of that (#561), the standard model permissions give more:
- add_usertoken: make a token for another active, non-superuser staff user
  whose permissions are all ones the maker has too.  The maker sees the
  secret, so they could act as that user; the rule stops that being a way to
  gain permissions.  Nobody makes a token for someone else who's a superuser.
- view_usertoken: see everyone's tokens.
- change_usertoken: rename anyone's token or bring its expiry forward, and
  revoke anyone's.
- delete_usertoken: delete anyone's.
A token's user is fixed when it's made: moving it would hand its secret's
holder a different user.  Make a new one for them and revoke the old one.
"""
from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.utils.html import escape, mark_safe

from authcustom.models import UserToken


def can(request, action):
  """ Has the model permission (add, view, change, delete) for everyone's tokens. """
  return request.user.is_superuser or request.user.has_perm(f'authcustom.{action}_usertoken')


def may_assign(request, user):
  """ May request.user make a token that acts as user? """
  me = request.user
  if user.pk == me.pk:
    return True
  if not can(request, 'add') or not (user.is_active and user.is_staff) or user.is_superuser:
    return False
  return me.is_superuser or user.get_all_permissions() <= me.get_all_permissions()


def assignable_users(request):
  """ The users request.user may make a token for, themselves included. """
  User = get_user_model()
  candidates = User.objects.filter(is_active=True, is_staff=True, is_superuser=False).exclude(pk=request.user.pk)
  pks = [u.pk for u in candidates if may_assign(request, u)] + [request.user.pk]
  return User.objects.filter(pk__in=pks).order_by('username')


def expiry_allowed(old, new):
  """ An expiry can be set, or brought forward, but never pushed back or removed. """
  return old is None or (new is not None and new <= old)


class UserTokenForm(forms.ModelForm):
  """ Making a token: a name, and optionally how long it lasts. """
  days = forms.IntegerField(min_value=1, max_value=3650, required=False,
                            help_text="Days until it expires. Leave empty for a token that doesn't expire.")

  class Meta:
    model = UserToken
    fields = ('name',)


class AssignUserTokenForm(UserTokenForm):
  """ Making a token, for yourself or for another staff user. """
  class Meta(UserTokenForm.Meta):
    fields = ('name', 'user')
    help_texts = {'user': "Who the token acts as. You'll see its secret once, to pass on to them. "
                          "Only staff users whose permissions you also have are listed, and never a superuser."}


class ChangeUserTokenForm(forms.ModelForm):
  """ Editing a token: its name, and an earlier expiry. """
  class Meta:
    model = UserToken
    fields = ('name', 'expiry_date')
    help_texts = {'expiry_date': "Can be set, or brought forward. To make a token last longer, make a new one."}

  def clean_expiry_date(self):
    new = self.cleaned_data.get('expiry_date')
    old = UserToken.objects.get(pk=self.instance.pk).expiry_date
    if not expiry_allowed(old, new):
      raise forms.ValidationError(
        f"This token expires {old:%Y-%m-%d %H:%M}; its expiry can be brought forward, not pushed back or removed.")
    return new


@admin.register(UserToken)
class UserTokenAdmin(admin.ModelAdmin):
  list_display = ('name', 'prefix', 'user', 'created_by', 'created', 'expiry_date', 'last_used', 'revoked')
  list_filter = ('revoked',)
  search_fields = ('name', 'prefix', 'user__username')
  actions = ['revoke']

  def mine(self, request):
    return request.user.is_active and request.user.is_staff

  def sees_all(self, request):
    return can(request, 'view') or can(request, 'change')

  # every staff user manages their own tokens, without model permissions
  def has_module_permission(self, request):
    return self.mine(request)

  def has_view_permission(self, request, obj=None):
    return self.mine(request) and (obj is None or obj.user_id == request.user.pk or self.sees_all(request))

  def has_add_permission(self, request):
    return self.mine(request)

  def has_change_permission(self, request, obj=None):
    # editing needs change_usertoken; a revoked token stays as it is
    return self.mine(request) and can(request, 'change') and (obj is None or not obj.revoked)

  def has_delete_permission(self, request, obj=None):
    return self.mine(request) and (obj is None or obj.user_id == request.user.pk or can(request, 'delete'))

  def get_actions(self, request):
    actions = super().get_actions(request)
    if self.sees_all(request) and not can(request, 'delete'):
      # the list shows others' tokens, which this user mustn't delete
      actions.pop('delete_selected', None)
    return actions

  def get_queryset(self, request):
    tokens = super().get_queryset(request).select_related('user', 'created_by')
    return tokens if self.sees_all(request) else tokens.filter(user=request.user)

  def formfield_for_foreignkey(self, db_field, request, **kwargs):
    if db_field.name == 'user':
      kwargs['queryset'] = assignable_users(request)
    return super().formfield_for_foreignkey(db_field, request, **kwargs)

  def get_changeform_initial_data(self, request):
    return {**super().get_changeform_initial_data(request), 'user': request.user.pk}

  def get_form(self, request, obj=None, **kwargs):
    if obj is not None:
      kwargs['form'] = ChangeUserTokenForm
      return super().get_form(request, obj, **kwargs)
    if not can(request, 'add'):
      kwargs['form'] = UserTokenForm
      return super().get_form(request, obj, **kwargs)
    kwargs['form'] = AssignUserTokenForm
    form = super().get_form(request, obj, **kwargs)

    class Form(form):
      def clean(self):
        # the choices are already only these users; this also refuses a
        # crafted POST, should they ever differ
        data = super().clean()
        user = data.get('user')
        if user is not None and not may_assign(request, user):
          self.add_error('user', "You can't make a token for this user.")
        return data
    return Form

  def get_fields(self, request, obj=None):
    if obj is None:
      return ('name', 'user', 'days') if can(request, 'add') else ('name', 'days')
    return ('name', 'prefix', 'user', 'created_by', 'created', 'expiry_date', 'last_used', 'revoked')

  def get_readonly_fields(self, request, obj=None):
    if obj is None:
      return ()
    fields = self.get_fields(request, obj)
    if self.has_change_permission(request, obj):
      return tuple(f for f in fields if f not in ChangeUserTokenForm.Meta.fields)
    return fields

  def save_model(self, request, obj, form, change):
    if change:
      # the form only edits the name and expiry; check again what's stored
      stored = UserToken.objects.get(pk=obj.pk)
      if obj.user_id != stored.user_id or stored.revoked or not expiry_allowed(stored.expiry_date, obj.expiry_date):
        raise PermissionDenied
      obj.save(update_fields=['name', 'expiry_date'])
      return
    user = form.cleaned_data.get('user') or request.user
    # fresh from the database, so its permissions are current
    user = get_user_model().objects.get(pk=user.pk)
    if not may_assign(request, user):
      raise PermissionDenied
    token, secret = UserToken.make(user, form.cleaned_data['name'], form.cleaned_data.get('days'),
                                   created_by=request.user)
    obj.pk = token.pk
    obj.refresh_from_db()
    usage = ("Use it as <code>Authorization: Token &lt;token&gt;</code>, or with mash: "
             "<code>connect &lt;url&gt; token &lt;token&gt;</code>.")
    if user.pk == request.user.pk:
      text = (f"Your API token, shown only this once: <code>{escape(secret)}</code><br>"
              f"{usage} It acts as you, with your permissions.")
    else:
      name = escape(user.username)
      text = (f"The API token for {name}, shown only this once: <code>{escape(secret)}</code><br>"
              f"{usage} It acts as {name}, with their permissions. Pass it to them over a safe channel.")
    self.message_user(request, mark_safe(text), messages.WARNING)

  @admin.action(description="Revoke selected tokens")
  def revoke(self, request, queryset):
    tokens = self.get_queryset(request).filter(pk__in=queryset.values('pk'), revoked=False)
    if not can(request, 'change'):
      tokens = tokens.filter(user=request.user)
    count = 0
    for token in tokens:
      token.revoked = True
      token.save(update_fields=['revoked'])
      count += 1
    self.message_user(request, f"Revoked {count} token" + ("" if count == 1 else "s") + ".")
