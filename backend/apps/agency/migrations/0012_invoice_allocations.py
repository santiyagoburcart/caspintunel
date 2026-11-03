"""v1.35.1: invoice ↔ money allocations (partial payments, adjustment / outside settlement)."""
import django.db.models.deletion
from django.db import migrations, models


def backfill(apps, schema_editor):
    """Invoices already paid by an approved agency payment get their allocation row (no status changes)."""
    Invoice = apps.get_model("agency", "AgencyInvoice")
    Alloc = apps.get_model("agency", "AgencyInvoiceAllocation")
    Item = apps.get_model("agency", "AgencyPaymentItem")
    Entry = apps.get_model("agency", "LedgerEntry")
    for inv in Invoice.objects.filter(status="paid"):
        it = Item.objects.filter(invoice=inv, payment__status="approved").select_related("payment").first()
        entry = None
        if it is not None:
            num = f"AP-{int(it.payment_id):06d}"
            entry = Entry.objects.filter(admin_username=inv.admin_username, kind="payment",
                                         note__startswith=f"agency payment {num}").first()
        Alloc.objects.create(invoice=inv, kind="payment", amount=inv.amount, ledger_entry=entry,
                             agency_payment=it.payment if it else None, note="backfill v1.35.1")
        Invoice.objects.filter(pk=inv.pk).update(paid_amount=inv.amount, settled_via="payment")


class Migration(migrations.Migration):
    dependencies = [("agency", "0011_portal_access_requests")]

    operations = [
        migrations.AddField("agencyinvoice", "paid_amount", models.DecimalField(decimal_places=0, default=0, max_digits=14)),
        migrations.AddField("agencyinvoice", "settled_via", models.CharField(blank=True, default="", max_length=12)),
        migrations.CreateModel(
            name="AgencyInvoiceAllocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("payment", "Agency payment"), ("manual", "Manual payment"),
                                                   ("adjustment", "Adjustment"), ("outside", "Paid outside the system"),
                                                   ("balance", "Covered by the balance")], max_length=12)),
                ("amount", models.DecimalField(decimal_places=0, max_digits=14)),
                ("auto", models.BooleanField(default=False, help_text="allocated oldest-first / by the invariant, not chosen by staff")),
                ("note", models.CharField(blank=True, default="", max_length=255)),
                ("created_by", models.CharField(blank=True, default="", max_length=150)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("released", models.BooleanField(default=False)),
                ("released_at", models.DateTimeField(blank=True, null=True)),
                ("release_reason", models.CharField(blank=True, default="", max_length=255)),
                ("agency_payment", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                     related_name="allocations", to="agency.agencypayment")),
                ("invoice", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="allocations",
                                              to="agency.agencyinvoice")),
                ("ledger_entry", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                   related_name="allocations", to="agency.ledgerentry")),
            ],
            options={"db_table": "agency_invoice_allocation", "ordering": ("id",)},
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
