"""Card-to-card payment flow (flowchart 1.3)."""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.common.models import write_audit
from apps.orders.models import Order, OrderStatus
from apps.orders.services import mark_paid_and_fulfill

from .models import BankCard, ConfirmedBy, Payment, PaymentMethod, PaymentStatus

log = logging.getLogger("caspintunel")


class PaymentError(Exception):
    pass


def default_bank_card() -> BankCard | None:
    """The card to credit a deposit to when nothing more specific is known.

    Card-to-card receipts (site + bot) and SMS auto-confirms don't reliably tell
    us *which* card the customer paid to. When there's exactly one active card,
    that's unambiguous — use it so the per-card deposit report is correct.
    With several active cards we leave it blank for the admin to set at approval.
    """
    cards = list(BankCard.objects.filter(is_active=True).order_by("sort_order", "id")[:2])
    return cards[0] if len(cards) == 1 else None


@transaction.atomic
def submit_receipt(*, order: Order, image, bank_card=None, user) -> Payment:
    if order.user_id != user.id:
        raise PaymentError("not your order")
    if order.status not in (OrderStatus.PENDING_PAYMENT,):
        raise PaymentError(f"order is {order.status}, cannot attach a receipt")
    if order.unique_expire_at and order.unique_expire_at < timezone.now():
        raise PaymentError("the payment reservation has expired; place the order again")

    # Two explicit steps (not update_or_create) so the FileField save is
    # unambiguous, and we can verify the file actually landed on storage.
    payment = Payment.objects.select_for_update().filter(order=order).first()
    if payment is None:
        payment = Payment(order=order)
    payment.method = PaymentMethod.CARD_MANUAL
    payment.amount = order.amount_unique
    payment.status = PaymentStatus.PENDING
    payment.bank_card = bank_card or default_bank_card()
    payment.reject_reason = ""
    payment.confirmed_by = None
    payment.confirmed_by_staff = None
    payment.confirmed_at = None
    payment.receipt_image = image
    payment.save()

    payment.refresh_from_db(fields=["receipt_image"])
    if not payment.receipt_image or not payment.receipt_image.storage.exists(payment.receipt_image.name):
        raise PaymentError("the receipt image could not be stored — please try again")

    write_audit(action="payment.receipt_uploaded", target=payment, staff=None)
    return payment


@transaction.atomic
def approve_payment(payment_id: int, *, actor=None, bank_card=None) -> Payment:
    payment = Payment.objects.select_for_update().select_related("order").get(pk=payment_id)
    if payment.status == PaymentStatus.APPROVED:
        return payment
    if payment.status != PaymentStatus.PENDING:
        raise PaymentError(f"payment is {payment.status}")

    payment.status = PaymentStatus.APPROVED
    payment.confirmed_by = ConfirmedBy.ADMIN
    payment.confirmed_at = timezone.now()
    if bank_card is not None:
        payment.bank_card = bank_card
    elif payment.bank_card_id is None:
        payment.bank_card = default_bank_card()
    payment.save(update_fields=["status", "confirmed_by", "confirmed_at", "bank_card", "updated_at"])

    mark_paid_and_fulfill(payment.order)
    write_audit(action="payment.approved", target=payment, staff=actor,
                detail={"order": payment.order_id})
    return payment


@transaction.atomic
def reject_payment(payment_id: int, *, reason: str, actor=None) -> Payment:
    payment = Payment.objects.select_for_update().select_related("order").get(pk=payment_id)
    if payment.status == PaymentStatus.APPROVED:
        raise PaymentError("cannot reject an approved payment")
    payment.status = PaymentStatus.REJECTED
    payment.reject_reason = reason
    payment.save(update_fields=["status", "reject_reason", "updated_at"])
    # order stays pending_payment so the customer can upload a new receipt
    write_audit(action="payment.rejected", target=payment, staff=actor, detail={"reason": reason})
    return payment
