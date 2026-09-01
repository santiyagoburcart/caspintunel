from django import forms
from django.contrib import admin, messages

from .client import TelegramError
from .config import client_for
from .models import RequiredChannel, TelegramConfig, TelegramStats


class TelegramConfigForm(forms.ModelForm):
    """Bot token is write-only in the admin — never rendered back."""

    token = forms.CharField(
        label="Bot token", required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="leave blank to keep the stored token",
    )

    class Meta:
        model = TelegramConfig
        exclude = ("token",)

    def save(self, commit=True):
        obj = super().save(commit=False)
        tok = self.cleaned_data.get("token")
        if tok:
            obj.token = tok
        if commit:
            obj.save()
        return obj


@admin.register(TelegramConfig)
class TelegramConfigAdmin(admin.ModelAdmin):
    form = TelegramConfigForm
    list_display = ("bot_type", "is_active", "has_token", "backup_chat_id", "updated_at")
    list_filter = ("is_active",)
    actions = ("test_connection",)

    @admin.display(boolean=True, description="token set")
    def has_token(self, obj):
        return bool(obj.token)

    @admin.action(description="Test bot connection (getMe)")
    def test_connection(self, request, queryset):
        for cfg in queryset:
            client = client_for(cfg.bot_type)
            if client is None:
                self.message_user(request, f"{cfg.bot_type}: not active / no token", messages.WARNING)
                continue
            try:
                me = client.get_me()
                self.message_user(request, f"{cfg.bot_type}: OK — @{me.get('username')}", messages.SUCCESS)
            except TelegramError as exc:
                self.message_user(request, f"{cfg.bot_type}: {exc}", messages.ERROR)


@admin.register(RequiredChannel)
class RequiredChannelAdmin(admin.ModelAdmin):
    list_display = ("channel_id", "title", "member_count", "is_active", "last_synced_at")
    list_editable = ("is_active",)


@admin.register(TelegramStats)
class TelegramStatsAdmin(admin.ModelAdmin):
    list_display = ("sampled_at", "bot_member_count", "overlap_bot_channels")
    readonly_fields = ("sampled_at",)
