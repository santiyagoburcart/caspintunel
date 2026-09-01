from django.contrib import admin

from .models import Page, Setting, SiteConfig, Theme


@admin.register(Setting)
class SettingAdmin(admin.ModelAdmin):
    list_display = ("key", "value", "value_type")
    list_filter = ("value_type",)
    search_fields = ("key",)


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    list_display = ("site_name_en", "site_domain", "updated_at")

    def has_add_permission(self, request):
        return not SiteConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Theme)
class ThemeAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_editable = ("is_active",)


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ("slug", "title_fa", "is_active", "updated_at")
    list_editable = ("is_active",)
    prepopulated_fields = {"slug": ("title_en",)}
