from django.db import migrations, models


class Migration(migrations.Migration):
    """Additive only (safe while the previous release still serves): the sender
    as reported by the device and a human-readable match / no-match note."""

    dependencies = [("payments_sms", "0004_latin_card_numbers")]

    operations = [
        migrations.AddField(
            model_name="smsmessage", name="sender",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="smsmessage", name="note",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
