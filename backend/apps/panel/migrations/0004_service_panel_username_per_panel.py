"""Multi-panel MP-Phase 1: service.panel_username is unique per panel, not
globally — the same username may exist on two different panels.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("panel", "0003_alter_panel_default_group_ids"),
    ]

    operations = [
        migrations.AlterField(
            model_name="service",
            name="panel_username",
            field=models.CharField(max_length=64),
        ),
        migrations.AddConstraint(
            model_name="service",
            constraint=models.UniqueConstraint(
                fields=("panel", "panel_username"), name="uniq_service_panel_username"
            ),
        ),
    ]
