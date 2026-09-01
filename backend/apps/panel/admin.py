from django import forms
from django.contrib import admin, messages

from .exceptions import PanelError
from .models import Panel, Service
from .services import sync_service


class PanelAdminForm(forms.ModelForm):
    """Panel password is write-only in the admin — the stored value is never
    rendered back into the form. Leave blank to keep the current password."""

    admin_password = forms.CharField(
        label="Panel admin password",
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="leave blank to keep the stored password",
    )

    class Meta:
        model = Panel
        exclude = ("admin_password_enc", "token_cache")

    def save(self, commit=True):
        obj = super().save(commit=False)
        pw = self.cleaned_data.get("admin_password")
        if pw:
            obj.admin_password_enc = pw
        if commit:
            obj.save()
        return obj


@admin.register(Panel)
class PanelAdmin(admin.ModelAdmin):
    form = PanelAdminForm
    list_display = ("name", "base_url", "admin_username", "has_password", "is_active",
                    "verify_ssl", "token_expires_at")
    list_filter = ("is_active",)
    readonly_fields = ("token_expires_at", "created_at", "updated_at")

    @admin.display(boolean=True, description="password set")
    def has_password(self, obj):
        return bool(obj.admin_password_enc)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = (
        "panel_username", "user", "panel", "status", "expire_strategy",
        "expire_at", "online_at", "last_synced_at",
    )
    list_filter = ("status", "expire_strategy", "panel", "source")
    search_fields = ("panel_username", "user__username", "subscription_url")
    raw_id_fields = ("user", "current_plan")
    readonly_fields = ("data_used", "online_at", "last_synced_at", "created_at", "updated_at")
    actions = ("action_sync",)

    @admin.action(description="Sync selected services from the panel")
    def action_sync(self, request, queryset):
        ok = 0
        for svc in queryset:
            try:
                sync_service(svc.id)
                ok += 1
            except PanelError as exc:
                self.message_user(request, f"{svc.panel_username}: {exc}", level=messages.ERROR)
        if ok:
            self.message_user(request, f"synced {ok} service(s)", level=messages.SUCCESS)
