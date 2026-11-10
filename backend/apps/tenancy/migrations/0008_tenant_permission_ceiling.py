from django.db import migrations, models

# the default template at the time of this release (apps/tenancy/staff.py DEFAULT_CEILING) — a literal, never imported
DEFAULT = ["discounts.manage", "discounts.view", "monitoring.view", "pages.manage", "payment.approve", "payment.view",
           "plans.manage", "roles.manage", "settings.manage", "sms.manage", "themes.manage", "tickets.assign", "tickets.close",
           "tickets.manage_topics", "tickets.reply", "tickets.view", "users.delete", "users.manage", "users.view"]


def fill(apps, schema_editor):
    Tenant = apps.get_model("tenancy", "Tenant")
    Tenant.objects.filter(is_default=False).update(permission_ceiling=DEFAULT)


class Migration(migrations.Migration):
    """v1.52 multi-tenant Phase 8: per-store permission ceiling (additive; existing stores get the default template)."""

    dependencies = [("tenancy", "0007_tenantbot")]

    operations = [
        migrations.AddField("tenant", "permission_ceiling", models.JSONField(blank=True, default=list)),
        migrations.RunPython(fill, migrations.RunPython.noop),
    ]
