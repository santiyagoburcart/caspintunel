import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Additive: a near-miss SMS deposit is linked to the open order for manual
    review (never approved). New nullable columns + a new payment-method choice."""

    dependencies = [
        ("orders", "0005_imported_order_type"),
        ("payments_sms", "0006_sms_amount_units"),
    ]

    operations = [
        migrations.AddField(
            model_name="smsmessage", name="mismatch_order",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="sms_mismatches", to="orders.order"),
        ),
        migrations.AddField(
            model_name="smsmessage", name="mismatch_kind",
            field=models.CharField(blank=True, db_default="", default="", max_length=4),
        ),
        migrations.AlterField(
            model_name="payment", name="method",
            field=models.CharField(choices=[("card_manual", "Card-to-card (manual)"), ("sms_auto", "SMS auto-match"),
                                            ("sms_mismatch", "SMS — amount mismatch (manual review)"),
                                            ("gateway", "Gateway")], max_length=12),
        ),
    ]
