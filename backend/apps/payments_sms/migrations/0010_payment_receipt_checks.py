"""v1.30.1: receipt duplicate checks — Payment.receipt_sha256 (backfilled from the stored
images; a missing file is skipped), receipt_ref and receipt_amount. Additive only."""
import hashlib

from django.db import migrations, models


def backfill_hashes(apps, schema_editor):
    Payment = apps.get_model("payments_sms", "Payment")
    for p in Payment.objects.exclude(receipt_image="").exclude(receipt_image__isnull=True).filter(receipt_sha256=""):
        try:
            with p.receipt_image.open("rb") as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
        except Exception:  # noqa: BLE001 — file gone / storage not mounted: leave it blank
            continue
        Payment.objects.filter(pk=p.pk).update(receipt_sha256=digest)


class Migration(migrations.Migration):

    dependencies = [
        ("payments_sms", "0009_payment_number_void"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment", name="receipt_sha256",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="payment", name="receipt_ref",
            field=models.CharField(blank=True, db_index=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="payment", name="receipt_amount",
            field=models.DecimalField(blank=True, decimal_places=0, max_digits=12, null=True),
        ),
        migrations.RunPython(backfill_hashes, migrations.RunPython.noop),
    ]
