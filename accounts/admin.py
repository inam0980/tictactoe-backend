from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "wins", "losses", "draws", "last_seen")
    fieldsets = UserAdmin.fieldsets + (
        ("Game profile", {"fields": ("avatar_url", "wins", "losses", "draws", "last_seen")}),
    )
