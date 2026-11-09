import django.db.models.deletion
from django.db import migrations, models

import apps.common.fields
import apps.tenancy.models


class Migration(migrations.Migration):
    """v1.49 multi-tenant Phase 6: a store's own Telegram bot (webhook mode, set by our staff). New table only (additive)."""

    dependencies = [("tenancy", "0006_tenant_quota_alert_level")]

    operations = [
        migrations.CreateModel(
            name="TenantBot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("token", apps.common.fields.EncryptedTextField(help_text="stored encrypted at rest; never returned by the API")),
                ("webhook_secret", apps.common.fields.EncryptedTextField(default=apps.tenancy.models._webhook_secret)),
                ("bot_id", models.BigIntegerField(help_text="Telegram id of the bot (getMe) — one store per bot", unique=True)),
                ("username", models.CharField(max_length=64)),
                ("state", models.CharField(choices=[("ok", "Webhook OK"), ("error", "Error")], default="ok", max_length=8)),
                ("last_error", models.CharField(blank=True, default="", max_length=500)),
                ("webhook_set_at", models.DateTimeField(blank=True, null=True)),
                ("last_check_at", models.DateTimeField(blank=True, null=True)),
                ("last_update_at", models.DateTimeField(blank=True, help_text="last update Telegram delivered", null=True)),
                ("alerted_at", models.DateTimeField(blank=True, help_text="the one 'bot broken' alert to us", null=True)),
                ("tenant", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="bot",
                                                to="tenancy.tenant")),
            ],
            options={"db_table": "tenant_bot"},
        ),
    ]
