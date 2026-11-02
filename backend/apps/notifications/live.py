"""Real-time nudges for the admin payments queue.

Every staff member allowed to see payments joins group `staff_payments`
(see consumers.StaffPaymentsConsumer). Whenever the queue can change — a new
order waiting for payment, a receipt upload, an SMS auto-approval, another
admin's approve/reject, reservations expiring — `push_payments_event` sends a
small event there. The browser then refetches the queue; the DB stays the
source of truth, so a missed frame only costs freshness, never correctness.
"""
from __future__ import annotations

import logging

from django.db import transaction

log = logging.getLogger("caspintunel")

STAFF_PAYMENTS_GROUP = "staff_payments"


def pending_payments_count() -> int:
    from apps.payments_sms.models import Payment, PaymentStatus

    return Payment.objects.live().filter(status=PaymentStatus.PENDING).count()


def _send(event: str, data: dict) -> None:
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            STAFF_PAYMENTS_GROUP,
            {
                "type": "payments.event",
                "payload": {"event": event, "pending_count": pending_payments_count(),
                            "agency_review": _agency_review(), **data},
            },
        )
    except Exception as exc:  # noqa: BLE001 — a push failure must never break the payment flow
        log.warning("staff payments push (%s) failed: %s", event, exc)


def push_payments_event(event: str, **data) -> None:
    """Queue a push for after the current transaction commits (so listeners
    that refetch see the new state), or send now when not in a transaction."""
    transaction.on_commit(lambda: _send(event, data))
    _web_push(event, data)


# v1.33: events that need a person also go out as a browser push to payment staff
_PUSH_EVENTS = {
    "receipt_uploaded": ("رسید جدید", "New receipt", "payment.approve"),
    "sms_mismatch": ("مبلغ نامطابق (پیامک)", "Amount mismatch (SMS)", "payment.approve"),
    "blu_mismatch": ("مبلغ نامطابق (بلو)", "Amount mismatch (Blu)", "payment.approve"),
    "rounded_approved": ("تأیید خودکار – مبلغ گرد شده", "Auto-approved — rounded amount", "payment.view"),
    "payment_pending_alert": ("پرداخت تأییدنشده", "Unconfirmed payment", "payment.approve"),
    "agency_pending_alert": ("واریز نماینده در انتظار", "Agency payment waiting", "agency.payments"),
}


def _web_push(event: str, data: dict) -> None:
    spec = _PUSH_EVENTS.get(event)
    if spec is None:
        return
    try:
        from .webpush import push_to_staff

        fa, en, perm = spec
        order = data.get("order_id")
        body = f"سفارش #{order} · order #{order}" if order else ""
        url = ("/agency/ledger/payments" if event.startswith("agency_")
               else f"/payments/{data['payment_id']}" if data.get("payment_id") else "/payments")
        push_to_staff(perm, f"{fa} · {en}", body, url=url, tag=f"{event}:{data.get('payment_id', '')}")
    except Exception as exc:  # noqa: BLE001
        log.warning("payments web push failed: %s", exc)


def _agency_review() -> int:
    """v1.34: agency payments waiting for review (their own badge, never in pending_count)."""
    try:
        from apps.agency.billing import badge

        return badge()
    except Exception:  # noqa: BLE001
        return 0
