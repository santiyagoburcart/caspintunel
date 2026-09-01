"""Card-to-card payment flow (flowchart 1.3)."""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.common.models import write_audit
from apps.orders.models import Order, OrderStatus
from apps.orders.services import mark_paid_and_fulfill

from .models import ConfirmedBy, Payment, PaymentMethod, PaymentStatus

log = logging.getLogger("caspintunel")


class PaymentError(Exception):
    pass


@transaction.atomic
def submit_receipt(*, order: Order, image, bank_card=None, user) -> Payment:
    if order.user_id != user.id:
        raise PaymentError("not your order")
    if order.status not in (OrderStatus.PENDING_PAYMENT,):
        raise PaymentError(f"order is {order.status}, cannot attach a receipt")
    if order.unique_expire_at and order.unique_expire_at < timezone.now():
        raise PaymentError("the payment reservation has expired; place the order again")

    payment, _ = Payment.objects.update_or_create(
        order=order,
        defaults=dict(
            method=PaymentMethod.CARD_MANUAL,
            amount=order.amount_unique,
            status=PaymentStatus.PENDING,
            receipt_image=image,
            bank_card=bank_card,
            reject_reason="",
            confirmed_by=None,
            confirmed_by_staff=None,
            confirmed_at=None,
        ),
    )
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
