"""SMS → invoice matching + auto-confirmation (flowchart 1.4)."""
from __future__ import annotations

import logging
import re

from django.db import transaction
from django.utils import timezone

from apps.common.models import write_audit
from apps.orders.models import Order, OrderStatus

from .models import (
    ConfirmedBy,
    Payment,
    PaymentMethod,
    PaymentStatus,
    SmsMessage,
    SmsSource,
)
from .parsing import candidate_amounts, normalize_digits

log = logging.getLogger("caspintunel")


def _norm_phone(value: str) -> str:
    digits = re.sub(r"\D", "", normalize_digits(value or ""))
    return digits[-10:] if len(digits) >= 10 else digits


def _resolve_source(sender: str | None):
    """
    Returns (SmsSource|None, allowed: bool).

    If any active `sms_source` rows exist they act as an allow-list — SMS from
    other senders is stored but never auto-confirmed.
    """
    active = list(SmsSource.objects.filter(is_active=True))
    if not active:
        return None, True
    if not sender:
        return None, False
    tail = _norm_phone(sender)
    for src in active:
        st = _norm_phone(src.phone_number)
        if st and tail and (st == tail or st.endswith(tail) or tail.endswith(st)):
            return src, True
    return None, False


@transaction.atomic
def ingest_sms(*, device, raw_text: str, sender: str | None = None, received_at=None) -> tuple[SmsMessage, dict]:
    source, allowed = _resolve_source(sender)
    msg = SmsMessage.objects.create(device=device, sms_source=source, raw_text=raw_text)
    if received_at:
        SmsMessage.objects.filter(pk=msg.pk).update(received_at=received_at)

    result: dict = {"message_id": msg.id, "matched": False}
    if not allowed:
        result["reason"] = "sender is not an allowed SMS source"
        return msg, result

    payment = match_sms_message(msg)
    if payment is not None:
        result.update(
            matched=True,
            order_id=payment.order_id,
            amount=str(payment.amount),
            payment_status=payment.status,
        )
    else:
        result["reason"] = "no pending order matches an amount in this SMS"
    return msg, result


def match_sms_message(msg: SmsMessage) -> Payment | None:
    if msg.matched_order_id:
        return None
    candidates = candidate_amounts(msg.raw_text)
    if not candidates:
        return None

    order = (
        Order.objects.select_for_update()
        .filter(status=OrderStatus.PENDING_PAYMENT, amount_unique_lock__in=candidates)
        .order_by("created_at")
        .first()
    )
    if order is None:
        return None

    msg.parsed_amount = order.amount_unique
    msg.matched_order = order
    msg.save(update_fields=["parsed_amount", "matched_order"])
    return _auto_confirm(order, msg)


def _auto_confirm(order: Order, msg: SmsMessage) -> Payment:
    from apps.orders.services import mark_paid_and_fulfill

    payment, _ = Payment.objects.update_or_create(
        order=order,
        defaults=dict(
            method=PaymentMethod.SMS_AUTO,
            amount=order.amount_unique,
            status=PaymentStatus.APPROVED,
            sms_message=msg,
            confirmed_by=ConfirmedBy.SYSTEM,
            confirmed_by_staff=None,
            confirmed_at=timezone.now(),
            reject_reason="",
        ),
    )
    mark_paid_and_fulfill(order)
    write_audit(
        action="payment.sms_auto_confirmed",
        target=payment,
        detail={"sms_message": msg.id, "order": order.id, "amount": str(order.amount_unique)},
    )
    log.info("SMS %s auto-confirmed order %s (%s)", msg.id, order.id, order.amount_unique)
    return payment
