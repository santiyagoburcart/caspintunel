"""SMS → invoice matching + auto-confirmation (flowchart 1.4).

The SMS amount is converted to tomans ONCE, with an explicit unit (parsing.py),
and an order is auto-confirmed only when that amount is EXACTLY its invoice
amount. No tolerance and no ×10 / ÷10 retries: an SMS whose amount equals an
open invoice only after a unit change (175,662 Rial vs a 175,662 Toman invoice)
is logged as "amount mismatch" for manual review and never approved.
"""
from __future__ import annotations

import logging
import re
from decimal import Decimal

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
from .parsing import RIAL, SmsAmount, deposit_amount, normalize_digits

log = logging.getLogger("caspintunel")


def _norm_phone(value: str) -> str:
    digits = re.sub(r"\D", "", normalize_digits(value or ""))
    return digits[-10:] if len(digits) >= 10 else digits


def _norm_name(value: str) -> str:
    """Alphanumeric sender names ("Resalat", "Bank-Resalat", "رسالت") compared
    case-insensitively without spaces/punctuation."""
    return re.sub(r"[\W_]+", "", normalize_digits(value or "")).casefold()


def mask_sms(text: str) -> str:
    """Card / account / long reference numbers → only their last 4 digits
    (for the admin SMS log). Amounts (<= 12 digits, no dots) stay readable."""
    def card(m):
        d = re.sub(r"\D", "", m.group(0))
        return "****-" + d[-4:] if len(d) >= 4 else m.group(0)
    text = re.sub(r"\d{4}[\s-]?[\d*]{4}[\s-]?[\d*]{4}[\s-]?\d{4}", card, normalize_digits(text or ""))
    text = re.sub(r"\d+(?:\.\d+){2,}", lambda m: m.group(0) if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", m.group(0))
                  else "***." + re.sub(r"\D", "", m.group(0))[-4:], text)   # 10.1234567.1 (not 1.750.000)
    return re.sub(r"\d{13,}", lambda m: "*" * 4 + m.group(0)[-4:], text)


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
    name = _norm_name(sender)
    for src in active:
        st = _norm_phone(src.phone_number)
        if st and tail and (st == tail or st.endswith(tail) or tail.endswith(st)):
            return src, True
        # a bank that sends from a name ("Resalat") instead of a number
        sn = _norm_name(src.phone_number)
        if sn and name and not sn.isdigit() and sn == name:
            return src, True
    return None, False


@transaction.atomic
def ingest_sms(*, device, raw_text: str, sender: str | None = None, received_at=None) -> tuple[SmsMessage, dict]:
    source, allowed = _resolve_source(sender)
    amount = deposit_amount(raw_text, source.amount_unit if source else RIAL)
    msg = SmsMessage.objects.create(
        device=device, sms_source=source, raw_text=raw_text, sender=(sender or "")[:64],
        parsed_amount=amount.toman if amount and amount.whole else None,
        parsed_raw=amount.raw if amount else None, parsed_unit=amount.unit if amount else "",
    )
    if received_at:
        SmsMessage.objects.filter(pk=msg.pk).update(received_at=received_at)

    result: dict = {"message_id": msg.id, "matched": False}
    if not allowed:
        result["reason"] = "sender is not an allowed SMS source"
        _note(msg, f"sender {sender!r} is not in Settings → bank numbers" if sender
              else "no sender reported, and an allow-list of bank numbers is set")
        return msg, result

    payment = match_sms_message(msg, amount)
    if payment is not None:
        result.update(
            matched=True,
            order_id=payment.order_id,
            amount=str(payment.amount),
            payment_status=payment.status,
        )
        _note(msg, f"matched order #{payment.order_id} ({payment.amount} T, SMS {amount.describe()}) — auto-confirmed")
        return msg, result
    suspect = unit_mismatch_order(amount)
    if suspect is not None:
        result["reason"] = "amount mismatch"
        _note(msg, f"amount mismatch — NOT approved, review by hand: SMS {amount.describe()}, "
                   f"order #{suspect.id} expects {suspect.amount_unique:,} T")
        log.warning("SMS %s: amount mismatch with order %s (%s vs %s T) — not approved",
                    msg.id, suspect.id, amount.describe(), suspect.amount_unique)
        return msg, result
    result["reason"] = "no pending order matches the amount in this SMS"
    _note(msg, _why_unmatched(amount))
    return msg, result


def _note(msg: SmsMessage, text: str) -> None:
    msg.note = text[:255]
    SmsMessage.objects.filter(pk=msg.pk).update(note=msg.note)


def _whole(values) -> list:
    return sorted({v for v in values if v > 0 and v == v.to_integral_value()})


def unit_mismatch_order(amount: SmsAmount | None) -> Order | None:
    """An open order whose invoice equals this SMS only after a ×10 / ÷10 unit
    change (the raw number, ten times / a tenth of the converted amount) — the
    classic Rial/Toman mix-up. Such an SMS is never approved, only flagged."""
    if amount is None:
        return None
    t, raw = amount.toman, Decimal(amount.raw)
    suspects = _whole([raw, raw * 10, raw / 10, t * 10, t / 10])
    suspects = [v for v in suspects if v != t]
    if not suspects:
        return None
    return (Order.objects.filter(status=OrderStatus.PENDING_PAYMENT, amount_unique__in=suspects)
            .order_by("-created_at").first())


def _why_unmatched(amount: SmsAmount | None) -> str:
    """Human-readable reason for the SMS log (what the admin needs to debug)."""
    if amount is None:
        return "no deposit amount found in the text (withdrawal, or a format the parser does not know)"
    if not amount.whole:
        return f"SMS {amount.describe()} — not a whole toman amount, no invoice can match"
    from datetime import timedelta

    near = (Order.objects.filter(amount_unique=amount.toman, created_at__gte=timezone.now() - timedelta(days=3))
            .order_by("-created_at").first())
    if near is None:
        return f"no order of exactly {amount.toman:,} T in the last 3 days (SMS {amount.describe()})"
    return f"order #{near.id} has this amount but is {near.status} (only pending, unexpired orders auto-confirm)"


def match_sms_message(msg: SmsMessage, amount: SmsAmount | None = None) -> Payment | None:
    """Auto-confirm the pending order whose invoice is EXACTLY the SMS amount in
    tomans. `amount` defaults to re-parsing the stored text with the source's unit."""
    if msg.matched_order_id:
        return None
    if amount is None:
        unit = msg.sms_source.amount_unit if msg.sms_source_id else RIAL
        amount = deposit_amount(msg.raw_text, unit)
    if amount is None or not amount.whole:
        return None

    order = (
        Order.objects.select_for_update()
        .filter(status=OrderStatus.PENDING_PAYMENT, amount_unique_lock=amount.toman)
        .order_by("created_at")
        .first()
    )
    if order is None or order.amount_unique != amount.toman:
        return None

    msg.parsed_amount = order.amount_unique
    msg.matched_order = order
    msg.save(update_fields=["parsed_amount", "matched_order"])
    return _auto_confirm(order, msg)


def _auto_confirm(order: Order, msg: SmsMessage) -> Payment:
    from apps.orders.services import mark_paid_and_fulfill

    from .services import default_bank_card

    payment, _ = Payment.objects.update_or_create(
        order=order,
        defaults=dict(
            method=PaymentMethod.SMS_AUTO,
            amount=order.amount_unique,
            status=PaymentStatus.APPROVED,
            sms_message=msg,
            bank_card=default_bank_card(),
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
    from apps.notifications.live import push_payments_event

    push_payments_event("sms_approved", order_id=order.id, payment_id=payment.id)
    log.info("SMS %s auto-confirmed order %s (%s)", msg.id, order.id, order.amount_unique)
    return payment
