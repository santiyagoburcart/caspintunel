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

    return Payment.objects.filter(status=PaymentStatus.PENDING).count()


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
                "payload": {"event": event, "pending_count": pending_payments_count(), **data},
            },
        )
    except Exception as exc:  # noqa: BLE001 — a push failure must never break the payment flow
        log.warning("staff payments push (%s) failed: %s", event, exc)


def push_payments_event(event: str, **data) -> None:
    """Queue a push for after the current transaction commits (so listeners
    that refetch see the new state), or send now when not in a transaction."""
    transaction.on_commit(lambda: _send(event, data))
