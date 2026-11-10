"""Failed store orders — «ساخت ناموفق» (v1.52.1, before the Phase 9 pilot).

A PAID order PasarGuard refused (`orders.tasks._provision_failed`: `provision_error` / `provision_failed_at`) is listed with the
panel's error and retried with an optional new account name — in the store's own panel (store staff: list = `payment.view`,
retry = `payment.approve`) and on our «فروشگاه» card (our staff, `agency.manage`, inside the store's context). The retry is the
existing `orders.services.retry_provision`: it clears the failure and runs fulfilment again for the SAME paid order — no new
order, no new payment, the customer is never charged again. Everything here runs in the CURRENT tenant context.
"""
from __future__ import annotations

from django.db import transaction


class RetryError(Exception):
    def __init__(self, en: str, fa: str, status: int = 400, *, code: str = "", suggestion: str = ""):
        super().__init__(en)
        self.en, self.fa, self.status, self.code, self.suggestion = en, fa, status, code, suggestion

    def payload(self) -> dict:
        out = {"detail": self.en, "detail_fa": self.fa}
        if self.code:
            out.update({"code": self.code, "suggestion": self.suggestion})
        return out


def payments():
    """Approved, not voided payments whose paid order was refused by PasarGuard (the Transactions tab's own filter)."""
    from apps.payments_sms.models import Payment

    return (Payment.objects.live().filter(status="approved", order__status="paid", order__provision_failed_at__isnull=False)
            .select_related("order", "order__user", "order__plan", "order__service").order_by("-order__provision_failed_at"))


def count() -> int:
    return payments().count()


def row(p) -> dict:
    o = p.order
    svc = o.service
    name = o.requested_account_name or (svc.panel_username if svc else "") or ""
    return {
        "order": o.id, "type": o.type, "tx": p.tx_number, "payment": p.id,
        "user": o.user.username if o.user_id else "", "plan_fa": o.plan.name_fa if o.plan_id else "",
        "plan_en": o.plan.name_en if o.plan_id else "", "amount": int(p.amount or 0),
        "account_name": name, "name_editable": o.type == "new" and not (svc and svc.subscription_url),
        "error": o.provision_error, "failed_at": o.provision_failed_at, "paid_at": p.confirmed_at,
    }


def rows(limit: int = 100) -> list[dict]:
    return [row(p) for p in payments()[:limit]]


def retry(order_id: int, staff, account_name: str | None = None) -> dict:
    """«تلاش دوباره» — same paid order, fulfilment again (result arrives as the usual live event / alert)."""
    from apps.orders.services import AccountNameRefused, OrderError, retry_provision

    p = payments().filter(order_id=order_id).first()
    if p is None:
        raise RetryError("this order is not waiting for a retry (already delivered, retried or not paid)",
                         "این سفارش در انتظار تلاش دوباره نیست (تحویل شده، در حال تلاش است یا پرداخت نشده)", 404)
    try:
        with transaction.atomic():
            retry_provision(p.order, staff, (account_name or "").strip() or None)
    except AccountNameRefused as exc:
        raise RetryError(exc.message("en", with_suggestion=True), exc.message("fa", with_suggestion=True),
                         code="account_name", suggestion=exc.suggestion) from exc
    except OrderError as exc:
        msg = str(exc)
        raise RetryError(msg, "این نام اکانت گرفته شده است" if "taken" in msg else msg) from exc
    return {"order": order_id, "message": "Retrying — the result arrives in a moment",
            "message_fa": "دوباره تلاش می‌شود — نتیجه تا چند لحظهٔ دیگر می‌رسد"}
