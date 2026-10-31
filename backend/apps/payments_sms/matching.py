"""SMS → invoice matching + auto-confirmation (flowchart 1.4).

The SMS amount is converted to tomans ONCE, with an explicit unit (parsing.py),
and an order is auto-confirmed only when that amount is EXACTLY its invoice
amount — not 1 toman less or more. No tolerance and no ×10 / ÷10 retries.

A deposit that is CLOSE to an open invoice (within ±20 %, or equal to it only
after a ×10 / ÷10 unit change) is never approved either: it is linked to that
order for manual review (SmsMessage.mismatch_order + "less"/"more"), the order
gets a pending "sms_mismatch" payment so it shows in the Payments queue (and
does not expire), and admins get a live notification. Same endpoint for the
iPhone Shortcut and the Android app.

Everything is judged at the moment the phone RECEIVED the SMS (`received_at`),
not when it reached us: the iPhone Shortcut queues SMS offline and uploads them
later (`inbound-batch`). An order counts as open for an SMS when it was waiting
for payment at that moment — still pending, or expired since but its deadline
was after the SMS arrived — and it existed by then (a few minutes of clock skew
allowed). An order created after the SMS arrived can never be paid by it.
"""
from __future__ import annotations

import logging
import re
from decimal import Decimal

from datetime import timedelta

from django.db import transaction
from django.db.models import Q
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


CLOCK_SKEW = timedelta(minutes=5)          # phone clock vs server clock


def open_orders_at(at=None, *, pending: bool | None = None):
    """Orders that were waiting for payment when the SMS arrived (see module doc).
    An expired order counts only if it was still open then: its deadline was not
    before the SMS and it was closed (expired by the timer, or dropped early for
    a newer order — `updated_at`) after the SMS arrived. pending=True/False
    narrows to still-pending / expired ones."""
    at = at or timezone.now()
    still = Q(status=OrderStatus.PENDING_PAYMENT)
    gone = Q(status=OrderStatus.EXPIRED, unique_expire_at__gte=at, updated_at__gte=at)
    cond = still if pending else gone if pending is False else (still | gone)
    return Order.objects.filter(cond, created_at__lte=at + CLOCK_SKEW)


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
def ingest_sms(*, device, raw_text: str, sender: str | None = None, received_at=None,
               dedupe_key: str | None = None) -> tuple[SmsMessage, dict]:
    """Store one SMS and try to match it. `dedupe_key` (batch uploads) is unique:
    a second copy raises IntegrityError before anything is matched."""
    source, allowed = _resolve_source(sender)
    amount = deposit_amount(raw_text, source.amount_unit if source else RIAL)
    now = timezone.now()
    msg = SmsMessage.objects.create(
        device=device, sms_source=source, raw_text=raw_text, sender=(sender or "")[:64],
        parsed_amount=amount.toman if amount and amount.whole else None,
        parsed_raw=amount.raw if amount else None, parsed_unit=amount.unit if amount else "",
        received_at=received_at or now, uploaded_at=now, dedupe_key=dedupe_key,
    )

    result: dict = {"message_id": msg.id, "matched": False, "late": msg.delivered_late}
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
        late = " (delivered late; order was open when the SMS arrived)" if msg.delivered_late else ""
        _note(msg, f"matched order #{payment.order_id} ({payment.amount} T, SMS {amount.describe()}) — auto-confirmed{late}")
        return msg, result
    # v1.32: a little LESS than exactly one open invoice + evidence → approved (rounded.py)
    from . import rounded

    rpay, rdec = rounded.try_sms(msg, amount)
    if rpay is not None:
        result.update(matched=True, order_id=rpay.order_id, amount=str(rpay.amount),
                      payment_status=rpay.status, rounded=True)
        return msg, result
    suspect = near_order(amount, msg.received_at)
    if suspect is not None:
        kind = flag_mismatch(msg, suspect, amount)
        if rdec is not None:
            rounded.remember(suspect, rdec.reason)
            _note(msg, f"{msg.note} · {rounded.note_text(rdec.reason)}")
        result.update(reason="amount mismatch", mismatch=kind, order_id=suspect.id)
        return msg, result
    result["reason"] = "no pending order matches the amount in this SMS"
    _note(msg, _why_unmatched(amount))
    return msg, result


def _note(msg: SmsMessage, text: str) -> None:
    msg.note = text[:255]
    SmsMessage.objects.filter(pk=msg.pk).update(note=msg.note)


def _whole(values) -> list:
    return sorted({v for v in values if v > 0 and v == v.to_integral_value()})


NEAR_RATIO = Decimal("0.20")


def near_order(amount: SmsAmount | None, at=None) -> Order | None:
    """The order open at `at` (see open_orders_at) this deposit is close to but does
    not equal: the ×10 / ÷10 unit case first, else the closest invoice within ±20 %."""
    if amount is None or amount.toman <= 0:
        return None
    unit = unit_mismatch_order(amount, at)
    if unit is not None:
        return unit
    t = Decimal(amount.toman)
    lo, hi = t / (1 + NEAR_RATIO), t / (1 - NEAR_RATIO)      # |t - invoice| <= 20 % of the invoice
    best = None
    for o in open_orders_at(at).filter(amount_unique__gte=lo.to_integral_value() - 1,
                                       amount_unique__lte=hi.to_integral_value() + 1).order_by("-created_at"):
        inv = Decimal(o.amount_unique)
        if inv <= 0 or inv == t or abs(t - inv) > inv * NEAR_RATIO:
            continue
        if best is None or abs(t - inv) < abs(t - Decimal(best.amount_unique)):
            best = o
    return best


def flag_mismatch(msg: SmsMessage, order: Order, amount: SmsAmount) -> str:
    """Link a near-miss deposit to its order for manual review. NEVER approves:
    a pending "sms_mismatch" payment puts the order in the Payments queue (an
    existing pending receipt just gets the SMS attached), and admins are told live."""
    from apps.notifications.live import push_payments_event

    from .services import default_bank_card

    kind = "less" if Decimal(amount.toman) < Decimal(order.amount_unique) else "more"
    msg.mismatch_order, msg.mismatch_kind = order, kind
    msg.save(update_fields=["mismatch_order", "mismatch_kind"])
    word = "LESS" if kind == "less" else "MORE"
    _note(msg, f"amount mismatch — {word} than invoice, NOT approved, review by hand: SMS {amount.describe()}, "
               f"order #{order.id} expects {order.amount_unique:,} T")
    payment = Payment.objects.select_for_update().filter(order=order).first()
    if payment is None:
        payment = Payment.objects.create(order=order, method=PaymentMethod.SMS_MISMATCH, amount=order.amount_unique,
                                         status=PaymentStatus.PENDING, sms_message=msg, bank_card=default_bank_card())
    elif payment.status == PaymentStatus.PENDING and payment.sms_message_id is None:
        payment.sms_message = msg
        payment.save(update_fields=["sms_message", "updated_at"])
    write_audit(action="payment.sms_amount_mismatch", target=payment,
                detail={"sms_message": msg.id, "order": order.id, "kind": kind,
                        "sms_toman": str(amount.toman), "invoice": str(order.amount_unique)})
    push_payments_event("sms_mismatch", order_id=order.id, payment_id=payment.id, kind=kind,
                        sms_amount=str(amount.toman), invoice_amount=str(order.amount_unique))
    log.warning("SMS %s: amount %s than order %s (%s vs %s T) — not approved",
                msg.id, kind, order.id, amount.describe(), order.amount_unique)
    return kind


def unit_mismatch_order(amount: SmsAmount | None, at=None) -> Order | None:
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
    return open_orders_at(at).filter(amount_unique__in=suspects).order_by("-created_at").first()


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

    # exactly this invoice amount, open when the SMS arrived (a queued SMS may
    # pay an order that expired while it waited in the phone)
    order = None
    for pending in (True, False):           # an open invoice first, then one that expired while the SMS was queued
        order = (open_orders_at(msg.received_at, pending=pending).select_for_update()
                 .filter(amount_unique=amount.toman).order_by("created_at").first())
        if order is not None:
            break
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
            auto_rule="",
            auto_reason={},
            shortfall=None,
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


# ---------------------------------------------------------------------------
# Blu Bank deposits (blu.py stores them; this matches them — same exact-amount rule)
# ---------------------------------------------------------------------------
BLU_CREATED_SKEW = timedelta(minutes=2)    # deposit seconds before the order row was written


def _blu_grace() -> timedelta:
    from .blu import late_grace_minutes

    return timedelta(minutes=late_grace_minutes()[0])


def _blu_window_ok(order: Order, at) -> bool:
    """Unique amounts are reused once a reservation ends: a deposit only pays an order
    when it happened between the order's creation and the end of its reservation (+grace)."""
    return order.created_at - BLU_CREATED_SKEW <= at <= order.unique_expire_at + _blu_grace()


def _blu_note(tx, text: str, **fields) -> None:
    from .models import BluTransaction

    tx.match_note = text[:255]
    for k, v in fields.items():
        setattr(tx, k, v)
    BluTransaction.objects.filter(pk=tx.pk).update(match_note=tx.match_note, **fields)


def _blu_paid_order(tx) -> Order | None:
    """An order of the same unique amount already paid (e.g. by the iPhone SMS first)
    whose window contains this deposit."""
    at, grace = tx.occurred_at, _blu_grace()
    candidates = (Order.objects.filter(amount_unique=tx.amount_toman,
                                       status__in=(OrderStatus.PAID, OrderStatus.COMPLETED),
                                       created_at__lte=at + BLU_CREATED_SKEW,
                                       unique_expire_at__gte=at - grace)
                  .order_by("-created_at"))
    for o in candidates[:5]:
        if Payment.objects.live().filter(order=o, status=PaymentStatus.APPROVED).exists():
            return o
    return None


def blu_amount(tx) -> SmsAmount:
    return SmsAmount(raw=int(tx.amount_irr), unit=RIAL, unit_from="sms", toman=Decimal(tx.amount_irr) / 10)


def match_blu_transaction(pk: int):
    """Auto-confirm the pending order whose unique amount is EXACTLY this deposit (whole
    tomans), inside the order's time window. Already paid → `duplicate`; close amount →
    flagged for manual review (never approved); otherwise it stays `unmatched`."""
    from .models import BluStatus, BluTransaction

    with transaction.atomic():
        tx = BluTransaction.objects.select_for_update().filter(pk=pk).first()
        if tx is None or tx.status != BluStatus.UNMATCHED or tx.matched_order_id:
            return tx
        if tx.amount_toman is None:
            _blu_note(tx, f"amount not a whole toman ({tx.amount_irr:,} Rial)")
            return tx
        at = tx.occurred_at
        order = (Order.objects.select_for_update()
                 .filter(status=OrderStatus.PENDING_PAYMENT, amount_unique_lock=tx.amount_toman).first())
        if order is not None and order.status != OrderStatus.PENDING_PAYMENT:
            order = None                     # paid by a concurrent SMS while we waited for the lock
        if order is not None and not _blu_window_ok(order, at):
            _blu_note(tx, f"order #{order.id} has this amount but the deposit is outside its window "
                          f"(created {order.created_at:%Y-%m-%d %H:%M}, reservation until "
                          f"{order.unique_expire_at:%Y-%m-%d %H:%M} UTC) — reused amount, not matched")
            return tx
        if order is not None:
            existing = Payment.objects.select_for_update().filter(order=order).first()
            if existing is not None and existing.status == PaymentStatus.APPROVED and existing.voided_at is None:
                _blu_note(tx, f"order #{order.id} is already paid (payment {existing.tx_number}) — duplicate",
                          status=BluStatus.DUPLICATE, matched_order=order)
                return tx
            confirm_blu(order, tx)
            return tx

        paid = _blu_paid_order(tx)
        if paid is not None:
            _blu_note(tx, f"order #{paid.id} was already paid (SMS / receipt) — duplicate, not approved again",
                      status=BluStatus.DUPLICATE, matched_order=paid)
            return tx
        # v1.32: a little LESS than exactly one open invoice + evidence → approved (rounded.py)
        from . import rounded

        rpay, rdec = rounded.try_blu(tx)
        if rpay is not None:
            return tx
        amount = blu_amount(tx)
        suspect = near_order(amount, at)
        if suspect is not None:
            flag_blu_mismatch(tx, suspect)
            if rdec is not None:
                rounded.remember(suspect, rdec.reason)
                _blu_note(tx, f"{tx.match_note} · {rounded.note_text(rdec.reason)}")
            return tx
        _blu_note(tx, f"no pending order of exactly {tx.amount_toman:,} T at the deposit time")
        return tx


def confirm_blu(order: Order, tx, *, staff=None, rounded: dict | None = None) -> Payment:
    """Approve `order` with Blu deposit `tx` — like _auto_confirm (or a staff attach when
    `staff` is given). `rounded` = the conditions of a rounded-amount approval (rounded.py):
    the payment then records the PAID amount and the shortfall. The caller holds the row
    locks inside a transaction."""
    from apps.notifications.live import push_payments_event
    from apps.orders.services import mark_paid_and_fulfill

    from .models import BluStatus
    from .services import _FULFILLABLE, default_bank_card

    existing = Payment.objects.filter(order=order).first()
    payment, _ = Payment.objects.update_or_create(
        order=order,
        defaults=dict(
            method=PaymentMethod.BLU_AUTO,
            amount=Decimal(tx.amount_toman) if rounded else order.amount_unique,
            status=PaymentStatus.APPROVED,
            blu_transaction=tx,
            auto_rule="rounded" if rounded else "",
            auto_reason=rounded or {},
            shortfall=(Decimal(order.amount_unique) - Decimal(tx.amount_toman)) if rounded else None,
            bank_card=(existing.bank_card if existing and existing.bank_card_id else default_bank_card()),
            confirmed_by=ConfirmedBy.ADMIN if staff else ConfirmedBy.SYSTEM,
            confirmed_by_staff=staff,
            confirmed_at=timezone.now(),
            reject_reason="",
            # the bank's document number feeds the duplicate-receipt warnings (checks.py)
            receipt_ref=(existing.receipt_ref if existing and existing.receipt_ref else (tx.reference or tx.receipt)),
        ),
    )
    if order.status in _FULFILLABLE:
        mark_paid_and_fulfill(order)
    detail = {"blu_transaction": tx.id, "order": order.id, "amount": str(order.amount_unique),
              "deposit_toman": str(tx.amount_toman) if tx.amount_toman is not None else None,
              "receipt": tx.receipt, "reference": tx.reference}
    if not rounded:          # a rounded approval writes its own audit entry (rounded._approved)
        write_audit(action="payment.blu_attached" if staff else "payment.blu_auto_confirmed",
                    staff=staff, target=payment, detail=detail)
        push_payments_event("blu_approved", order_id=order.id, payment_id=payment.id)
    how = f"attached by {staff.username}" if staff else "auto-confirmed"
    if rounded:
        from .rounded import note_text

        how = note_text(rounded)
    _blu_note(tx, f"matched order #{order.id} ({order.amount_unique:,} T) — {how}",
              status=BluStatus.MATCHED, matched_order=order, matched_payment=payment)
    log.info("Blu %s %s order %s (%s T)", tx.id, how, order.id, order.amount_unique)
    return payment


def flag_blu_mismatch(tx, order: Order) -> str:
    """A deposit close to an open invoice: never approved. A pending "blu_mismatch" payment
    puts the order in the Payments queue (an existing pending receipt gets the deposit
    attached); staff get a live event + Telegram. The deposit stays `unmatched`, linked."""
    from apps.common.staff_alert import alert_staff
    from apps.notifications.live import push_payments_event

    from .services import default_bank_card

    t, inv = Decimal(tx.amount_toman), Decimal(order.amount_unique)
    kind = "less" if t < inv else "more"
    payment = Payment.objects.select_for_update().filter(order=order).first()
    if payment is None:
        payment = Payment.objects.create(order=order, method=PaymentMethod.BLU_MISMATCH, amount=order.amount_unique,
                                         status=PaymentStatus.PENDING, blu_transaction=tx,
                                         bank_card=default_bank_card(), receipt_ref=tx.reference or tx.receipt)
    elif payment.status == PaymentStatus.PENDING and payment.blu_transaction_id is None:
        payment.blu_transaction = tx
        payment.save(update_fields=["blu_transaction", "updated_at"])
    word = "LESS" if kind == "less" else "MORE"
    _blu_note(tx, f"amount mismatch — {word} than invoice, NOT approved, review by hand: deposit "
                  f"{tx.amount_toman:,} T, order #{order.id} expects {order.amount_unique:,} T",
              matched_order=order)
    write_audit(action="payment.blu_amount_mismatch", target=payment,
                detail={"blu_transaction": tx.id, "order": order.id, "kind": kind,
                        "deposit_toman": str(tx.amount_toman), "invoice": str(order.amount_unique)})
    push_payments_event("blu_mismatch", order_id=order.id, payment_id=payment.id, kind=kind,
                        sms_amount=str(tx.amount_toman), invoice_amount=str(order.amount_unique))
    fa = "کمتر" if kind == "less" else "بیشتر"
    transaction.on_commit(lambda: alert_staff(
        f"⚠️ مبلغ نامطابق (بلو): واریز {tx.amount_toman:,} تومان، {fa} از فاکتور سفارش #{order.id} "
        f"({order.amount_unique:,} تومان). خودکار تأیید نشد — در صف پرداخت بررسی کنید.\n"
        f"Blu amount mismatch: deposit {tx.amount_toman:,} T vs order #{order.id} invoice "
        f"{order.amount_unique:,} T — review it in the payment queue.",
        perm="payment.approve", dedupe_key=f"blu:mismatch:{tx.id}"))
    log.warning("Blu %s: amount %s than order %s (%s vs %s T) — not approved",
                tx.id, kind, order.id, tx.amount_toman, order.amount_unique)
    return kind
