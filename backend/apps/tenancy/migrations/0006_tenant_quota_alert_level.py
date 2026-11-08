from django.db import migrations, models


class Migration(migrations.Migration):
    """v1.46 multi-tenant Phase 4: which quota warning was last sent to the store's reseller (additive)."""

    dependencies = [("tenancy", "0005_tenantdomain_phase3")]

    operations = [migrations.AddField("tenant", "quota_alert_level", models.PositiveSmallIntegerField(default=0))]
