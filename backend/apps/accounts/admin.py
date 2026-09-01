from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Permission, Role, Staff, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "name", "email", "email_verified", "source", "is_active", "created_at")
    list_filter = ("is_active", "email_verified", "source", "language", "is_legacy", "is_staff")
    search_fields = ("username", "name", "email", "phone", "referral_code", "telegram_username")
    ordering = ("-created_at",)
    readonly_fields = ("referral_code", "created_at", "updated_at", "last_login")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Profile", {"fields": ("name", "email", "email_verified", "phone", "bank_card_number", "language")}),
        ("Telegram", {"fields": ("telegram_id", "telegram_username")}),
        ("Referral", {"fields": ("referral_code", "referred_by")}),
        ("Flags", {"fields": ("source", "is_legacy", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("username", "password1", "password2", "email", "name", "phone")}),
    )


class RolePermissionInline(admin.TabularInline):
    model = Role.permissions.through
    extra = 0


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    filter_horizontal = ("permissions",)


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ("username", "role", "is_active", "is_superadmin", "last_login")
    list_filter = ("is_active", "is_superadmin", "role")
    search_fields = ("username",)
    readonly_fields = ("password_hash", "last_login", "created_at", "updated_at")
