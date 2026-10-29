"""Warnings shown on a payment in the approval queue (v1.30.1, incident 2026-10-29:
order #30 was approved with a screenshot of the transfer that SMS had already matched
to order #29). Read-only: nothing here changes a payment, it only points staff at the
linked records before they approve.

Kinds:
- amount_mismatch   the amount on the receipt ≠ the order's unique amount
- recent_sms        the same customer had a payment approved by bank SMS within 24 h
- duplicate_image   the same receipt image (sha256) is on another payment
- duplicate_ref     the same bank document / tracking number is on another payment
- renewal_waiting   a renewal order whose service already has another paid renewal waiting
"""
from __future__ import annotations

import hashlib
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from .models import Payment, PaymentMethod, PaymentStatus

RECENT_SMS_WINDOW = timedelta(hours=24)
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_ref(raw) -> str:
    """A bank document / tracking number as digits only (Persian / Arabic digits accepted)."""
    return re.sub(r"\D", "", str(raw or "").translate(_DIGITS))[:40]


def parse_amount(raw, unit: str = "toman") -> Decimal | None:
    """The receipt amount typed by staff / customer → tomans. `unit` is explicit
    (rial | toman) — never guessed (same rule as SMS amounts)."""
    digits = re.sub(r"\D", "", str(raw if raw is not None else "").translate(_DIGITS))
    if not digits:
        return None
    try:
        value = Decimal(digits)
    except InvalidOperation:
        return None
    if unit == "rial":
        if value % 10:
            raise ValueError("a Rial amount must end in 0 to convert to tomans")
        value = value / 10
    return value


def image_sha256(fileobj) -> str:
    h = hashlib.sha256()
    if hasattr(fileobj, "seek"):
        fileobj.seek(0)
    for chunk in (fileobj.chunks() if hasattr(fileobj, "chunks") else iter(lambda: fileobj.read(65536), b"")):
        h.update(chunk)
    if hasattr(fileobj, "seek"):
        fileobj.seek(0)
    return h.hexdigest()


def _link(p: Payment) -> dict:
    o = p.order
    return {
        "id": p.id, "tx": p.tx_number, "order_id": p.order_id, "user": o.user.username if o else None,
        "amount": p.amount, "status": p.status, "method": p.method, "created_at": p.created_at,
        "confirmed_at": p.confirmed_at, "voided": p.voided_at is not None,
        "service_id": o.service_id if o else None,
    }


def _others(p: Payment):
    return Payment.objects.exclude(pk=p.pk).select_related("order", "order__user").order_by("-id")


def payment_warnings(p: Payment) -> list[dict]:
    order = p.order
    out: list[dict] = []

    if p.receipt_amount is not None and order is not None and p.receipt_amount != order.amount_unique:
        out.append({"kind": "amount_mismatch", "receipt_amount": p.receipt_amount,
                    "invoice_amount": order.amount_unique, "diff": p.receipt_amount - order.amount_unique})

    if order is not None:
        around = p.created_at
        recent = [x for x in _others(p).filter(
            order__user_id=order.user_id, status=PaymentStatus.APPROVED, voided_at__isnull=True,
            method__in=(PaymentMethod.SMS_AUTO, PaymentMethod.SMS_MISMATCH),
            confirmed_at__gte=around - RECENT_SMS_WINDOW, confirmed_at__lte=around + RECENT_SMS_WINDOW)[:5]]
        if recent:
            links = [_link(x) for x in recent]
            for link in links:
                link["same_service"] = bool(order.service_id) and link["service_id"] == order.service_id
            out.append({"kind": "recent_sms", "payments": links})

    if p.receipt_sha256:
        same = list(_others(p).filter(receipt_sha256=p.receipt_sha256)[:5])
        if same:
            out.append({"kind": "duplicate_image", "payments": [_link(x) for x in same]})

    if p.receipt_ref:
        same = list(_others(p).filter(receipt_ref=p.receipt_ref)[:5])
        if same:
            out.append({"kind": "duplicate_ref", "ref": p.receipt_ref, "payments": [_link(x) for x in same]})

    if order is not None and order.type == "renew" and order.service_id:
        from apps.orders.services import waiting_renewal

        w = waiting_renewal(order.service)
        if w is not None and w["order"].id != order.id:
            out.append({"kind": "renewal_waiting", "order_id": w["order"].id, "state": w["state"],
                        "plan_name": w["plan"].name_fa if w["plan"] else None})
    return out
