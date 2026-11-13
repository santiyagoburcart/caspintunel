"""Unconfirmed payment alert (v1.33).

A payment still `pending` (a receipt waiting, or an SMS / Blu deposit that did not match and
is under review) for more than `pending_payment_alert_minutes` (Settings → Alerts, default 5,
0 = off) gets ONE Telegram alert to staff with `payment.approve` (+ browser push + live
`payment_pending_alert` toast in the panel), with a link to the payment. `pending_alerted_at`
makes sure it never repeats. When such a payment is later approved / rejected / deleted, one
silent "resolved" follow-up goes out (`pending_resolved_at`).

Only payments created in the last 24 h are considered, so turning it on never floods staff
with old rows.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from .models import Payment, PaymentStatus

log = logging.getLogger("caspintunel")

DEFAULT_MINUTES = 5
LOOKBACK = timedelta(hours=24)
MAX_PER_RUN = 30


def minutes() -> int:
    from apps.settings_app.utils import get_setting

    try:
        return max(0, int(get_setting("pending_payment_alert_minutes", DEFAULT_MINUTES)))
    except (TypeError, ValueError):
        return DEFAULT_MINUTES


def _why(p: Payment) -> tuple[str, str]:
    if p.receipt_image:
        return "رسید در انتظار بررسی", "receipt waiting for review"
    if p.method in ("sms_mismatch", "blu_mismatch"):
        return "واریز با مبلغ نامطابق", "deposit with a different amount"
    return "در انتظار تأیید", "waiting for approval"


def run(now=None) -> dict:
    from apps.common.links import admin_link
    from apps.common.staff_alert import alert_staff
    from apps.notifications.live import push_payments_event

    now = now or timezone.now()
    n = minutes()
    out = {"alerted": 0, "resolved": 0, "minutes": n}
    if n > 0:
        due = (Payment.objects.live().select_related("order", "order__user")
               .filter(status=PaymentStatus.PENDING, pending_alerted_at__isnull=True,
                       created_at__lte=now - timedelta(minutes=n), created_at__gte=now - LOOKBACK)
               .order_by("created_at")[:MAX_PER_RUN])
        for p in due:
            # claim it first: two workers never send the same alert
            if not Payment.objects.filter(pk=p.pk, pending_alerted_at__isnull=True).update(pending_alerted_at=now):
                continue
            age = int((now - p.created_at).total_seconds() // 60)
            fa, en = _why(p)
            link = admin_link(f"/payments/{p.id}")
            text = (f"⏳ پرداخت تأییدنشده {p.tx_number} — سفارش #{p.order_id} ({p.order.user.username}) · "
                    f"{p.amount:,} تومان · {fa} · {age} دقیقه\n"
                    f"Unconfirmed payment {p.tx_number} — order #{p.order_id}, {p.amount:,} T, {en}, {age} min\n{link}")
            from apps.tenancy.context import store_id

            # v1.60.1: a store's staff decide from its bot (approve / reject buttons → telegram/bot/sales_bot._payment_cb)
            buttons = None
            if store_id():
                from apps.telegram.bot.sales_bot import payment_buttons

                buttons = payment_buttons(p.id)
            alert_staff(text, perm="payment.approve", dedupe_key=f"pending-alert:{p.id}", ttl=86400, buttons=buttons)
            push_payments_event("payment_pending_alert", order_id=p.order_id, payment_id=p.id, minutes=age,
                                tx=p.tx_number)
            out["alerted"] += 1
        out["agency_alerted"] = _agency(now, n)
    # one silent follow-up when an alerted payment got handled
    done = (Payment.objects.filter(pending_alerted_at__isnull=False, pending_resolved_at__isnull=True,
                                   pending_alerted_at__gte=now - LOOKBACK)
            .exclude(status=PaymentStatus.PENDING, voided_at__isnull=True)[:MAX_PER_RUN])
    for p in done:
        if not Payment.objects.filter(pk=p.pk, pending_resolved_at__isnull=True).update(pending_resolved_at=now):
            continue
        state_fa = "حذف شد" if p.voided_at else {"approved": "تأیید شد", "rejected": "رد شد"}.get(p.status, p.status)
        state_en = "deleted" if p.voided_at else p.status
        alert_staff(f"✅ پرداخت {p.tx_number} (سفارش #{p.order_id}) {state_fa}.\n"
                    f"Payment {p.tx_number} (order #{p.order_id}) {state_en}.",
                    perm="payment.approve", silent=True, dedupe_key=f"pending-resolved:{p.id}", ttl=86400)
        out["resolved"] += 1
    return out


def _agency(now, n: int) -> int:
    """v1.34: agency payments under review (receipt / near-miss deposit) longer than N minutes —
    one alert to staff with agency.payments, never repeated."""
    from apps.agency.models import AgencyPayment
    from apps.common.links import admin_link
    from apps.common.staff_alert import alert_staff
    from apps.notifications.live import push_payments_event

    sent = 0
    due = (AgencyPayment.objects.filter(status=AgencyPayment.PENDING_REVIEW, pending_alerted_at__isnull=True,
                                        updated_at__lte=now - timedelta(minutes=n), created_at__gte=now - LOOKBACK)
           .order_by("created_at")[:MAX_PER_RUN])
    for p in due:
        if not AgencyPayment.objects.filter(pk=p.pk, pending_alerted_at__isnull=True).update(pending_alerted_at=now):
            continue
        age = int((now - (p.receipt_uploaded_at or p.updated_at)).total_seconds() // 60)
        alert_staff(f"⏳ واریز نماینده {p.number} ({p.payer_username}) {age} دقیقه است بررسی نشده · {p.amount_unique:,} تومان\n"
                    f"Agency payment {p.number} ({p.payer_username}) waiting {age} min.\n{admin_link('/agency/ledger/payments')}",
                    perm="agency.payments", dedupe_key=f"agency-pending:{p.id}", ttl=86400)
        push_payments_event("agency_pending_alert", payment_id=p.id, minutes=age, number=p.number)
        sent += 1
    return sent
