"""v1.59 data fix (agency payments, OUR store only — a platform table):
1. an unfinished checkout past its timer becomes `expired` (the beat job normally does this within ~5 min);
2. an expired / unfinished payment whose invoices are ALL paid becomes `superseded` with the approved payment that paid them
   (the newest one holding all its invoices), e.g. AP-000026 → AP-000028.
Prints what it changed (shown in ./update.sh). Reverse = no-op (the rows stay as fixed)."""
from django.db import migrations
from django.utils import timezone


def _num(pk):
    return f"AP-{pk:06d}"


def forwards(apps, schema_editor):
    P = apps.get_model("agency", "AgencyPayment")
    Item = apps.get_model("agency", "AgencyPaymentItem")
    Inv = apps.get_model("agency", "AgencyInvoice")
    now = timezone.now()
    expired = []
    for p in P.objects.filter(status="pending_payment", unique_expire_at__lt=now):
        p.status, p.amount_unique_lock = "expired", None
        p.save(update_fields=["status", "amount_unique_lock", "updated_at"])
        expired.append(_num(p.pk))
    superseded = []
    for p in P.objects.filter(status__in=("expired", "pending_payment")):
        ids = set(Item.objects.filter(payment_id=p.pk).values_list("invoice_id", flat=True))
        if not ids or Inv.objects.filter(pk__in=ids).exclude(status="paid").exists():
            continue
        by = None
        for c in P.objects.filter(status="approved", items__invoice_id__in=ids).exclude(pk=p.pk).distinct().order_by("-confirmed_at", "-id"):
            if ids <= set(Item.objects.filter(payment_id=c.pk).values_list("invoice_id", flat=True)):
                by = c
                break
        p.status, p.superseded_by, p.amount_unique_lock = "superseded", by, None
        p.save(update_fields=["status", "superseded_by", "amount_unique_lock", "updated_at"])
        superseded.append(f"{_num(p.pk)}→{_num(by.pk) if by else 'paid otherwise'}")
    print(f"\n  agency payments: expired now {expired or 'none'} · superseded {superseded or 'none'}")


class Migration(migrations.Migration):
    dependencies = [("agency", "0016_agencypayment_superseded_by_and_more")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
