from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class RetobizUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Retobiz", {"fields": ("store", "role")}),)
