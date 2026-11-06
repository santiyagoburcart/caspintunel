"""v1.42.2: when a payment is approved by any route (manual invoice, staff receipt approval, SMS, agency payment), an
unmatched Blu deposit that belongs to it is linked after commit (blu_link.auto_link_*). Never approves anything."""
import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Payment, PaymentMethod, PaymentStatus

log = logging.getLogger("caspintunel")
_SKIP = (PaymentMethod.BLU_AUTO, PaymentMethod.CASH, PaymentMethod.GATEWAY)


def _later(fn, pk):
    def run():
        try:
            fn(pk)
        except Exception as exc:  # noqa: BLE001 — linking is a convenience, never break an approval
            log.warning("Blu auto-link for %s failed: %s", pk, exc)
    transaction.on_commit(run)


@receiver(post_save, sender=Payment, dispatch_uid="blu_autolink_payment")
def _payment_saved(sender, instance, raw=False, **kwargs):
    if raw or instance.status != PaymentStatus.APPROVED or instance.blu_transaction_id or instance.voided_at \
            or instance.method in _SKIP:
        return
    from .blu_link import auto_link_payment

    _later(auto_link_payment, instance.pk)


def connect_agency():
    from apps.agency.models import AgencyPayment

    def _agency_saved(sender, instance, raw=False, **kwargs):
        if raw or instance.status != "approved" or instance.blu_transaction_id:
            return
        from .blu_link import auto_link_agency_payment

        _later(auto_link_agency_payment, instance.pk)

    post_save.connect(_agency_saved, sender=AgencyPayment, dispatch_uid="blu_autolink_agency", weak=False)
