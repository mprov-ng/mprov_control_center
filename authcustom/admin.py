from django.contrib.auth.admin import UserAdmin
from django.contrib import admin
from django.contrib.auth.models import User
class UserAdminCustom(UserAdmin):
  """ Django's user admin, with a "Change Password" button on the user form. """
  change_form_template ='admin/user_change_form.html'

admin.site.unregister(User)
admin.site.register(User, UserAdminCustom)