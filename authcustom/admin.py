from django.contrib.auth.admin import UserAdmin
from django.contrib import admin
from django.contrib.auth.models import User
class UserAdminCustom(UserAdmin):
  change_form_template ='admin/user_change_form.html'

admin.site.unregister(User)
admin.site.register(User, UserAdminCustom)

# the API Keys pages, marked as legacy.
from . import apikey_admin  # noqa: E402,F401
