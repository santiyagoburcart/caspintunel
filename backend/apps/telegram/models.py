from django.db import models

from apps.common.fields import EncryptedTextField


class BotType(models.TextChoices):
    SALES = "sales", "Sales bot"
    BACKUP = "backup", "Backup bot"


class TelegramConfig(models.Model):
    """Two separate bots, separate tokens (data-model · Module 7 · `telegram_config`)."""

    bot_type = models.CharField(max_length=6, choices=BotType.choices, unique=True)
    token = EncryptedTextField(blank=True, help_text="stored encrypted at rest")
    proxy_url = models.CharField(max_length=255, null=True, blank=True)
    backup_chat_id = models.BigIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "telegram_config"

    def __str__(self) -> str:
        return f"{self.bot_type} bot"


class RequiredChannel(models.Model):
    """A forced-join channel for the sales bot (data-model · Module 7)."""

    channel_id = models.CharField(max_length=100, help_text="@username or -100... id")
    title = models.CharField(max_length=150, blank=True)
    invite_link = models.URLField(
        blank=True,
        help_text="optional; needed for private channels so users get a join button",
    )
    member_count = models.IntegerField(default=0)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "required_channel"
        ordering = ("id",)

    def __str__(self) -> str:
        return self.title or self.channel_id


class TelegramStats(models.Model):
    """Periodic snapshot (data-model · Module 7 · `telegram_stats`)."""

    bot_member_count = models.IntegerField(default=0)
    overlap_bot_channels = models.IntegerField(default=0)
    sampled_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "telegram_stats"
        ordering = ("-sampled_at",)

    def __str__(self) -> str:
        return f"stats @ {self.sampled_at:%Y-%m-%d %H:%M}"
