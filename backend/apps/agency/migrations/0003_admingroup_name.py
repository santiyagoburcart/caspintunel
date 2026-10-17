from django.db import migrations, models


class Migration(migrations.Migration):
    """Additive: a display name for account groups (PAMP has none)."""

    dependencies = [("agency", "0002_portal_ledger")]

    operations = [
        migrations.AddField(model_name="admingroup", name="name",
                            field=models.CharField(blank=True, default="", max_length=100)),
    ]
