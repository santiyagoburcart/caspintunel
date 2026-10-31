"""Rounded-amount auto-approve (v1.32), for Blu deposits and bank SMS alike.

Customers sometimes round the unique invoice amount DOWN (249,350 → 248,000). Such a deposit
is approved automatically only when ALL of these hold:

  1. it is below the invoice (never above), by at most max(rounded_max_toman, rounded_max_percent
     of the invoice), default max(2,000 T, 1 %);
  2. it lies inside the order's time window: the same guard as exact matching (SMS:
     `matching.open_orders_at`, Blu: pending order + `_blu_window_ok`);
  3. exactly ONE open order fits (1 + 2), whoever's it is. Two or more → no approval;
  4. and at least one piece of evidence: the customer uploaded a receipt for that order
     (receipts are only accepted inside the reservation, `services.submit_receipt`), OR the payer
     card's last 4 digits (Blu) match a card this customer paid from before (an earlier Blu
     deposit matched to one of their orders).

Then the payment is approved like an exact match, with auto_rule "rounded"
(«تأیید خودکار – مبلغ گرد شده»), amount = what was paid, shortfall = the difference (Accounting
counts the paid amount). Staff get a Telegram + panel alert. A Super Admin can undo it
(«لغو تأیید»): `undo` voids it like a transaction delete (keep service by default) and puts the
deposit back for manual review.

Anything else goes to the queue as «مبلغ نامطابق», exactly as before (matching.near_order /
flag_mismatch), with the evaluated conditions stored on the pending payment (`auto_reason`).
An exact amount never reaches this module, and ×10 / ÷10 unit look-alikes are far outside the
tolerance. Setting `rounded_auto_enabled` (default on) switches the rule off.

A receipt uploaded AFTER the deposit arrived triggers a re-check (`retry_for_order`, Celery):
that is the usual order (pay first, then upload the receipt).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.common.models import write_audit
from apps.orders.models import Order, OrderStatus

from .models import AutoRule, Payment, PaymentStatus

log = logging.getLogger("caspintunel")

LABEL_FA = "تأیید خودکار – مبلغ گرد شده"
LABEL_EN = "Auto-approved — rounded amount"
UNDO_REASON = "لغو تأیید خودکار – مبلغ گرد شده"


def config() -> dict:
    from apps.settings_app.utils import get_setting

    try:
        percent = Decimal(str(get_setting("rounded_max_percent", "1") or "0"))
    except InvalidOperation:
        percent = Decimal("1")
    try:
        min_toman = Decimal(int(get_setting("rounded_max_toman", 2000) or 0))
    except (TypeError, ValueError):
        min_toman = Decimal(2000)
    return {"enabled": bool(get_setting("rounded_auto_enabled", True)), "max_toman": max(Decimal(0), min_toman),
            "max_percent": min(max(Decimal(0), percent), Decimal(10))}


def tolerance(invoice, cfg: dict) -> Decimal:
    """The largest shortfall allowed for this invoice: max(fixed tomans, percent of the invoice)."""
    pct = (Decimal(invoice) * cfg["max_percent"] / 100).to_integral_value(rounding="ROUND_FLOOR")
    return max(cfg["max_toman"], pct)


@dataclass
class Decision:
    approve: bool
    order: Order | None
    reason: dict = field(default_factory=dict)


def _candidates(deposit: Decimal, at, source: str, cfg: dict) -> list[Order]:
    from .matching import _blu_window_ok, open_orders_at

    p = cfg["max_percent"] / 100
    hi = deposit + cfg["max_toman"]
    if p < 1:
        hi = max(hi, deposit / (1 - p))
    if source == "sms":
        qs = open_orders_at(at)
    else:
        qs = Order.objects.filter(status=OrderStatus.PENDING_PAYMENT)
    qs = qs.filter(amount_unique__gt=deposit, amount_unique__lte=math.ceil(hi) + 1).order_by("created_at")
    out = []
    for o in qs[:20]:
        inv = Decimal(o.amount_unique)
        if not (deposit < inv and inv - deposit <= tolerance(inv, cfg)):
            continue
        if source != "sms" and not _blu_window_ok(o, at):
            continue
        out.append(o)
    return out


def _has_receipt(order: Order) -> bool:
    return (Payment.objects.live().filter(order=order, status=PaymentStatus.PENDING)
            .exclude(receipt_image="").exclude(receipt_image__isnull=True).exists())


def _known_card(order: Order, last4: str, exclude_tx: int | None) -> bool:
    """The payer card (last 4) paid one of this customer's orders before (an approved Blu deposit)."""
    from .models import BluStatus, BluTransaction

    if not last4 or len(last4) != 4:
        return False
    qs = BluTransaction.objects.filter(status=BluStatus.MATCHED, payer_last4=last4,
                                       matched_order__user_id=order.user_id,
                                       matched_payment__status=PaymentStatus.APPROVED,
                                       matched_payment__voided_at__isnull=True)
    if exclude_tx:
        qs = qs.exclude(pk=exclude_tx)
    return qs.exists()


def _already_used(deposit: Decimal, at, source: str) -> Order | None:
    """The same deposit seen twice (iPhone SMS + Blu): an order already auto-approved with exactly
    this paid amount whose window contains it. Such a deposit is never approved again."""
    from .matching import BLU_CREATED_SKEW, _blu_grace

    grace = _blu_grace()
    p = (Payment.objects.live().filter(status=PaymentStatus.APPROVED, auto_rule=AutoRule.ROUNDED, amount=deposit,
                                       order__created_at__lte=at + BLU_CREATED_SKEW,
                                       order__unique_expire_at__gte=at - grace)
         .select_related("order").order_by("-confirmed_at").first())
    return p.order if p else None


def evaluate(deposit, at, *, source: str, payer_last4: str = "", tx_id: int | None = None) -> Decision | None:
    """None when the rule does not concern this deposit (off, not whole, no open order just above
    it, e.g. an over-payment). Otherwise a Decision with the conditions in `reason`."""
    cfg = config()
    if not cfg["enabled"] or deposit is None:
        return None
    try:
        deposit = Decimal(deposit)
    except (InvalidOperation, TypeError):
        return None
    if deposit <= 0 or deposit != deposit.to_integral_value():
        return None
    cands = _candidates(deposit, at, source, cfg)
    if not cands:
        return None
    reason = {"rule": AutoRule.ROUNDED, "source": source, "deposit": str(deposit),
              "max_toman": str(cfg["max_toman"]), "max_percent": str(cfg["max_percent"]),
              "candidates": len(cands), "candidate_orders": [o.id for o in cands[:5]], "window": True,
              "checked_at": timezone.now().isoformat()}
    if len(cands) > 1:
        reason.update(applied=False, why_not="multiple_orders")
        return Decision(False, None, reason)
    order = cands[0]
    inv = Decimal(order.amount_unique)
    reason.update(order=order.id, invoice=str(inv), shortfall=str(inv - deposit), tolerance=str(tolerance(inv, cfg)))
    used = _already_used(deposit, at, source)
    if used is not None:
        reason.update(applied=False, why_not="deposit_already_used", used_order=used.id)
        return Decision(False, order, reason)
    receipt = _has_receipt(order)
    card = _known_card(order, payer_last4, tx_id)
    reason.update(receipt=receipt, card_last4=payer_last4 or "", card_known=card)
    if not (receipt or card):
        reason.update(applied=False, why_not="no_evidence")
        return Decision(False, order, reason)
    reason["applied"] = True
    return Decision(True, order, reason)


def note_text(reason: dict) -> str:
    """One line for logs / SMS log / Blu tab: which conditions matched."""
    if not reason:
        return ""
    bits = [f"{reason.get('candidates', 0)} order(s) fit"]
    if "shortfall" in reason:
        bits.append(f"short {Decimal(reason['shortfall']):,} T ≤ {Decimal(reason['tolerance']):,} T")
    if reason.get("receipt"):
        bits.append("receipt uploaded")
    if reason.get("card_known"):
        bits.append(f"known card ****{reason.get('card_last4')}")
    why = {"multiple_orders": "2+ orders fit", "no_evidence": "no receipt and an unknown card",
           "deposit_already_used": f"deposit already approved order #{reason.get('used_order')}"}.get(
        reason.get("why_not", ""), "")
    head = "rounded amount — auto-approved" if reason.get("applied") else f"rounded rule not applied ({why})"
    return f"{head}: " + ", ".join(bits)


# ---------------------------------------------------------------------------
# approve / remember why not
# ---------------------------------------------------------------------------
def _lock_open(order: Order, at, source: str) -> Order | None:
    from .matching import _blu_window_ok, open_orders_at

    if source == "sms":
        return open_orders_at(at).select_for_update().filter(pk=order.pk).first()
    o = Order.objects.select_for_update().filter(pk=order.pk, status=OrderStatus.PENDING_PAYMENT).first()
    return o if o is not None and _blu_window_ok(o, at) else None


def approve_sms(order: Order, msg, deposit: Decimal, reason: dict) -> Payment:
    from apps.orders.services import mark_paid_and_fulfill

    from .models import ConfirmedBy, PaymentMethod
    from .services import _FULFILLABLE, default_bank_card

    existing = Payment.objects.select_for_update().filter(order=order).first()
    payment, _ = Payment.objects.update_or_create(order=order, defaults=dict(
        method=PaymentMethod.SMS_AUTO, amount=deposit, status=PaymentStatus.APPROVED, sms_message=msg,
        bank_card=(existing.bank_card if existing and existing.bank_card_id else default_bank_card()),
        confirmed_by=ConfirmedBy.SYSTEM, confirmed_by_staff=None, confirmed_at=timezone.now(), reject_reason="",
        auto_rule=AutoRule.ROUNDED, auto_reason=reason, shortfall=Decimal(order.amount_unique) - deposit))
    msg.matched_order = order
    msg.mismatch_order, msg.mismatch_kind = None, ""
    msg.note = note_text(reason)[:255]
    msg.save(update_fields=["matched_order", "mismatch_order", "mismatch_kind", "note"])
    if order.status in _FULFILLABLE:
        mark_paid_and_fulfill(order)
    _approved(payment, order, reason, source="sms", ref=f"sms {msg.id}")
    return payment


def approve_blu(order: Order, tx, reason: dict) -> Payment:
    from .matching import confirm_blu

    payment = confirm_blu(order, tx, rounded=reason)
    _approved(payment, order, reason, source="blu", ref=f"blu {tx.id}")
    return payment


def _approved(payment: Payment, order: Order, reason: dict, *, source: str, ref: str) -> None:
    from apps.common.staff_alert import alert_staff
    from apps.notifications.live import push_payments_event

    write_audit(action="payment.rounded_auto_confirmed", target=payment, detail={
        "order": order.id, "source": source, "invoice": str(order.amount_unique), "paid": str(payment.amount),
        "shortfall": str(payment.shortfall), "reason": reason})
    push_payments_event("rounded_approved", order_id=order.id, payment_id=payment.id, source=source,
                        paid=str(payment.amount), invoice_amount=str(order.amount_unique),
                        shortfall=str(payment.shortfall))
    ev = []
    if reason.get("receipt"):
        ev.append("رسید آپلود شده / receipt")
    if reason.get("card_known"):
        ev.append(f"کارت آشنا / known card ****{reason.get('card_last4')}")
    tx, sh = payment.tx_number, f"{payment.shortfall:,}"
    text = (f"✅ {LABEL_FA}: سفارش #{order.id} — فاکتور {order.amount_unique:,}، واریز {payment.amount:,} تومان "
            f"(کسری {sh} تومان). {' · '.join(ev)}\n"
            f"{LABEL_EN}: order #{order.id}, invoice {order.amount_unique:,} T, paid {payment.amount:,} T "
            f"(short {sh} T). Undo from transaction {tx} if this is wrong.")
    transaction.on_commit(lambda: alert_staff(text, perm="payment.approve", dedupe_key=f"rounded:{payment.id}"))
    log.info("rounded auto-approve: %s → order %s (paid %s, invoice %s)", ref, order.id, payment.amount,
             order.amount_unique)


def remember(order: Order | None, reason: dict | None) -> None:
    """Keep why the rule did not apply on the order's pending review payment (shown in the queue)."""
    if order is None or not reason:
        return
    Payment.objects.filter(order=order, status=PaymentStatus.PENDING, voided_at__isnull=True).update(
        auto_reason=reason)


def try_sms(msg, amount) -> tuple[Payment | None, Decision | None]:
    """Called by matching.ingest_sms when no invoice equals the SMS amount (inside its transaction)."""
    if amount is None or not getattr(amount, "whole", False):
        return None, None
    deposit = Decimal(amount.toman)
    d = evaluate(deposit, msg.received_at, source="sms")
    if d is None or not d.approve:
        return None, d
    order = _lock_open(d.order, msg.received_at, "sms")
    if order is None:
        return None, None
    return approve_sms(order, msg, deposit, d.reason), d


def try_blu(tx) -> tuple[Payment | None, Decision | None]:
    """Called by matching.match_blu_transaction (row-locked, inside its transaction)."""
    d = evaluate(tx.amount_toman, tx.occurred_at, source="blu", payer_last4=tx.payer_last4, tx_id=tx.pk)
    if d is None or not d.approve:
        return None, d
    order = _lock_open(d.order, tx.occurred_at, "blu")
    if order is None:
        return None, None
    return approve_blu(order, tx, d.reason), d


def retry_for_order(order_id: int) -> str:
    """A receipt was uploaded: re-check the deposits that were linked to this order as LESS than
    its invoice (Blu deposit or SMS waiting for review). Approves at most one."""
    from .models import BluStatus, BluTransaction, SmsMessage

    with transaction.atomic():
        order = Order.objects.select_for_update().filter(pk=order_id).first()
        if order is None or order.status not in (OrderStatus.PENDING_PAYMENT, OrderStatus.EXPIRED):
            return "not open"
        txs = (BluTransaction.objects.select_for_update()
               .filter(status=BluStatus.UNMATCHED, matched_order=order, amount_toman__lt=order.amount_unique)
               .order_by("occurred_at"))
        for tx in txs:
            p, d = try_blu(tx)
            if p is not None:
                return f"approved by blu {tx.id}"
            remember(order, d.reason if d else None)
        msgs = (SmsMessage.objects.select_for_update()
                .filter(mismatch_order=order, mismatch_kind="less", matched_order__isnull=True,
                        parsed_amount__isnull=False).order_by("received_at"))
        for msg in msgs:
            d = evaluate(msg.parsed_amount, msg.received_at, source="sms")
            if d is not None and d.approve and d.order.pk == order.pk and _lock_open(order, msg.received_at, "sms"):
                approve_sms(order, msg, Decimal(msg.parsed_amount), d.reason)
                return f"approved by sms {msg.id}"
            remember(order, d.reason if d else None)
    return "no change"


# ---------------------------------------------------------------------------
# undo («لغو تأیید»)
# ---------------------------------------------------------------------------
def undo(payment_id: int, *, staff, reason: str = "", service_action: str = "keep") -> Payment:
    """Void a rounded auto-approval like a transaction delete (Super Admin; keep service by
    default) and hand the deposit back for manual review."""
    from .models import BluStatus, BluTransaction, SmsMessage
    from .voiding import VoidError, require_superadmin, void_payment

    require_superadmin(staff)
    p0 = Payment.objects.filter(pk=payment_id).first()
    if p0 is None:
        raise VoidError("transaction not found", "not_found")
    if p0.auto_rule != AutoRule.ROUNDED:
        raise VoidError("this payment was not auto-approved by the rounded-amount rule", "invalid")
    why = UNDO_REASON + (f": {reason.strip()}" if (reason or "").strip() else "")
    p = void_payment(payment_id, staff=staff, reason=why, service_action=service_action or "keep")
    with transaction.atomic():
        who = getattr(staff, "username", "staff")
        released = {}
        for tx in BluTransaction.objects.select_for_update().filter(matched_payment=p):
            tx.status, tx.matched_payment = BluStatus.UNMATCHED, None
            tx.match_note = f"rounded auto-approval undone by {who} — review by hand"[:255]
            tx.save(update_fields=["status", "matched_payment", "match_note"])
            released["blu_transaction"] = tx.id
        if p.sms_message_id:
            SmsMessage.objects.filter(pk=p.sms_message_id).update(
                matched_order=None, mismatch_order=p.order_id, mismatch_kind="less",
                note=f"rounded auto-approval undone by {who} — review by hand"[:255])
            released["sms_message"] = p.sms_message_id
        write_audit(action="payment.rounded_undone", staff=staff, target=p, detail={
            "tx": p.tx_number, "order": p.order_id, "paid": str(p.amount), "shortfall": str(p.shortfall),
            "service_action": service_action or "keep", **released})
    return p
