"""Backfill bank_card on historical approved/pending payments.

Card-to-card and SMS-auto payments used to be saved with bank_card = NULL, so the
per-card deposit report (BankCard.deposit_total) always showed 0. When exactly
one active bank card exists the destination is unambiguous, so link every
unlinked payment to it. With several active cards we can't know which one and
leave those rows for an admin to set at approval time.
"""
from django.db import migrations


def link_sole_card(apps, schema_editor):
    BankCard = apps.get_model("payments_sms", "BankCard")
    Payment = apps.get_model("payments_sms", "Payment")

    active = list(BankCard.objects.filter(is_active=True).order_by("sort_order", "id")[:2])
    if len(active) != 1:
        return
    Payment.objects.filter(bank_card__isnull=True).update(bank_card=active[0])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("payments_sms", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(link_sole_card, noop),
    ]
