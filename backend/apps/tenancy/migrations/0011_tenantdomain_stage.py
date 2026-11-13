from django.db import migrations, models


class Migration(migrations.Migration):
    """v1.60: the step a store domain is on + since when + the one «stuck» alert (tenancy/domains.py::_track_stage)."""

    dependencies = [("tenancy", "0010_storeimport_importrecord")]

    operations = [
        migrations.AddField("tenantdomain", "stage", models.CharField(blank=True, default="", max_length=8)),
        migrations.AddField("tenantdomain", "stage_since", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("tenantdomain", "stage_alerted", models.CharField(blank=True, default="", max_length=8)),
    ]
