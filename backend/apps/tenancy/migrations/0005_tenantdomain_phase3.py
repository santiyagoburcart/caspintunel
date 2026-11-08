from django.db import migrations, models


class Migration(migrations.Migration):
    """v1.45 multi-tenant Phase 3 (store domains + TLS): additive fields only (backward compatible)."""

    dependencies = [("tenancy", "0004_backfill_release_c")]

    operations = [
        migrations.AddField("tenantdomain", "include_www", models.BooleanField(default=True)),
        migrations.AddField("tenantdomain", "proxied", models.BooleanField(default=False)),
        migrations.AddField("tenantdomain", "verified_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("tenantdomain", "cert_issued_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("tenantdomain", "dns", models.JSONField(blank=True, default=dict)),
        migrations.AddField("tenantdomain", "health", models.JSONField(blank=True, default=dict)),
        migrations.AddField("tenantdomain", "unhealthy_since", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("tenantdomain", "cert_failures", models.PositiveSmallIntegerField(default=0)),
        migrations.AddField("tenantdomain", "retry_token", models.PositiveIntegerField(default=0)),
    ]
