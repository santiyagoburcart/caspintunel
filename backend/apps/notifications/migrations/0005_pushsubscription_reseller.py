from django.db import migrations, models


class Migration(migrations.Migration):
    """v1.38.2: Web Push for agency resellers (/agency/ portal). Additive (db_default) — the previous
    release keeps working while this runs."""

    dependencies = [("notifications", "0004_pushsubscription")]

    operations = [
        migrations.AddField(
            model_name="pushsubscription",
            name="reseller",
            field=models.CharField(blank=True, db_default="", db_index=True, default="", max_length=255),
        ),
    ]
