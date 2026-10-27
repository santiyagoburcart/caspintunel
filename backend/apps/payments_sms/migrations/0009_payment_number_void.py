"""v1.25: Payment.number (TX-000123, = id, backfilled) and the Super Admin void
(soft delete) fields. Additive only — the previous release keeps working."""
import django.db.models.deletion
from django.db import migrations, models


def backfill(apps, schema_editor):
    Payment = apps.get_model("payments_sms", "Payment")
    Payment.objects.filter(number__isnull=True).update(number=models.F("id"))


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0012_staff_display_name"),
        ("payments_sms", "0008_sms_batch_queue"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment", name="number",
            field=models.PositiveIntegerField(blank=True, editable=False, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="payment", name="voided_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="payment", name="voided_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="voided_payments", to="accounts.staff"),
        ),
        migrations.AddField(
            model_name="payment", name="void_reason",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="payment", name="void_service_action",
            field=models.CharField(blank=True, choices=[("keep", "Keep the order and service"),
                                                        ("disable", "Cancel the order, disable the service on PasarGuard"),
                                                        ("delete", "Cancel the order, delete the service on PasarGuard")],
                                   default="", max_length=8),
        ),
        migrations.AddField(
            model_name="payment", name="void_prev_order_status",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
