"""Card-to-card payment flow (flowchart 1.3)."""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.common.models import write_audit
from apps.notifications.dispatch import notify_user
from apps.notifications.live import push_payments_event
from apps.notifications.models import NotificationType
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
    push_payments_event("receipt_uploaded", order_id=order.id, payment_id=payment.id)
    return payment


# order states from which an approval must (re)start fulfilment
_FULFILLABLE = (OrderStatus.PENDING_PAYMENT, OrderStatus.EXPIRED, OrderStatus.REJECTED, OrderStatus.FAILED)


def _staff_or_none(actor):
    from apps.accounts.models import Staff

    return actor if isinstance(actor, Staff) else None


@transaction.atomic
def approve_payment(payment_id: int, *, actor=None, bank_card=None) -> Payment:
    """Approve a payment and deliver the service — the ONLY way into
    `approved`, whatever the previous status (pending, or a rejected payment
    the admin changed their mind about). Idempotent: an approved payment is
    returned as is, and an order that is already paid/completed is never
    provisioned again."""
    payment = Payment.objects.select_for_update().select_related("order").get(pk=payment_id)
    if payment.status == PaymentStatus.APPROVED:
        return payment
    if payment.status not in (PaymentStatus.PENDING, PaymentStatus.REJECTED):
        raise PaymentError(f"payment is {payment.status}")
    order = Order.objects.select_for_update().get(pk=payment.order_id)
    previous = payment.status

    payment.status = PaymentStatus.APPROVED
    payment.confirmed_by = ConfirmedBy.ADMIN
    payment.confirmed_by_staff = _staff_or_none(actor)
    payment.confirmed_at = timezone.now()
    payment.reject_reason = ""
    if bank_card is not None:
        payment.bank_card = bank_card
    elif payment.bank_card_id is None:
        payment.bank_card = default_bank_card()
    payment.save(update_fields=["status", "confirmed_by", "confirmed_by_staff", "confirmed_at",
                                "reject_reason", "bank_card", "updated_at"])

    payment.order = order
    if order.status in _FULFILLABLE:
        mark_paid_and_fulfill(order)
    else:
        # already paid (fulfilment queued) or completed: never provision twice
        log.info("approve_payment(%s): order %s is %s — not fulfilling again", payment.id, order.id, order.status)
    notify_user(
        payment.order.user,
        title="سفارش شما تأیید شد",
        body=f"پرداخت سفارش #{payment.order_id} تأیید شد و سرویس شما در حال آماده‌سازی است.",
        title_en="Your order was confirmed",
        body_en=f"Payment for order #{payment.order_id} was approved and your service is being prepared.",
        ntype=NotificationType.ORDER_CONFIRMED,
        via_site=True, via_bot=True, via_email=True,
    )
    write_audit(action="payment.approved", target=payment, staff=actor,
                detail={"order": payment.order_id, "from": previous})
    push_payments_event("payment_approved", order_id=payment.order_id, payment_id=payment.id,
                        by=getattr(actor, "username", None))
    return payment


@transaction.atomic
def reject_payment(payment_id: int, *, reason: str, actor=None) -> Payment:
    """Reject a payment AND its order: the order becomes `rejected` (shown red
    with the reason, never reused for a new purchase) and its unique amount is
    released. Buying again creates a new order with a new unique amount."""
    payment = Payment.objects.select_for_update().select_related("order").get(pk=payment_id)
    if payment.status == PaymentStatus.APPROVED:
        raise PaymentError("cannot reject an approved payment")
    order = Order.objects.select_for_update().get(pk=payment.order_id)
    if order.status in (OrderStatus.PAID, OrderStatus.COMPLETED):
        raise PaymentError(f"order is {order.status}, cannot reject its payment")
    payment.status = PaymentStatus.REJECTED
    payment.reject_reason = reason
    payment.confirmed_by_staff = _staff_or_none(actor)
    payment.save(update_fields=["status", "reject_reason", "confirmed_by_staff", "updated_at"])
    if order.status in (OrderStatus.PENDING_PAYMENT, OrderStatus.EXPIRED):
        order.status = OrderStatus.REJECTED
        order.sync_unique_lock()   # releases the unique amount
        order.save(update_fields=["status", "amount_unique_lock", "updated_at"])
    notify_user(
        order.user,
        title="پرداخت شما رد شد",
        body=f"پرداخت سفارش #{order.id} رد شد. دلیل: {reason}\nبرای خرید دوباره یک سفارش جدید ثبت کنید.",
        title_en="Your payment was rejected",
        body_en=f"Payment for order #{order.id} was rejected. Reason: {reason}\nPlace a new order to buy again.",
        ntype=NotificationType.EVENT,
        via_site=True, via_bot=True, via_email=True,
    )
    write_audit(action="payment.rejected", target=payment, staff=actor, detail={"reason": reason, "order": order.id})
    push_payments_event("payment_rejected", order_id=payment.order_id, payment_id=payment.id,
                        by=getattr(actor, "username", None))
    return payment
