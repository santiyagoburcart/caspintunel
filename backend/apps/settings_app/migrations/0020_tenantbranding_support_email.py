from django.db import migrations, models


class Migration(migrations.Migration):
    """v1.51 multi-tenant Phase 7 Release B: a store's support email (Reply-To of its mail). Additive."""

    dependencies = [("settings_app", "0019_tenantbranding_tenantsetting")]

    operations = [
        migrations.AddField("tenantbranding", "support_email", models.EmailField(blank=True, default="", max_length=254)),
    ]
