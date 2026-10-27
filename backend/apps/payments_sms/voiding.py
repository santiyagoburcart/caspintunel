"""Super Admin "Delete transaction" = void (soft delete) — never a hard delete.

A voided payment keeps its row but is left out of the Transactions list (unless "Show
deleted"), the review queue, and every total: the Transactions cards, Accounting,
Analytics (revenue, LTV, cohorts), card deposit reports, CRM figures. It can be restored
for VOID_RESTORE_DAYS. Each void / restore writes an audit entry (who, reason, amount).

For the linked order / service the Super Admin picks (default "keep"):
  keep     — order and service untouched (only the money leaves the books);
  disable  — order → cancelled, service disabled on PasarGuard (panel first, then mirrored);
  delete   — order → cancelled, service deleted on PasarGuard and here.
A still-pending payment always closes its order (cancelled) so an SMS can never approve it
afterwards. A restore puts the payment and the order status back; PasarGuard changes are
not undone (a deleted account is gone; a disabled one is re-enabled from its service page).
"""
from __future__ import annotations

from datetime import timedelta

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.models import write_audit
from apps.notifications.live import push_payments_event

from .models import Payment, PaymentStatus, VoidServiceAction

VOID_RESTORE_DAYS = 30
CANCELLING = (VoidServiceAction.DISABLE, VoidServiceAction.DELETE)


class VoidError(Exception):
    STATUS = {"forbidden": 403, "not_found": 404, "already": 409, "not_voided": 409, "expired": 409,
              "busy": 409, "panel_error": 502}

    def __init__(self, message: str, code: str = "invalid", field: str | None = None):
        super().__init__(message)
        self.code, self.field = code, field

    @property
    def status(self) -> int:
        return self.STATUS.get(self.code, 400)

    def payload(self) -> dict:
        return {"detail": str(self), "code": self.code, "field": self.field}


def require_superadmin(staff) -> None:
    if not getattr(staff, "is_superadmin", False):
        raise VoidError("only a Super Admin can delete or restore transactions", "forbidden")


def restorable_until(p: Payment):
    return p.voided_at + timedelta(days=VOID_RESTORE_DAYS) if p.voided_at else None


def can_restore(p: Payment) -> bool:
    return p.voided_at is not None and timezone.now() <= restorable_until(p)


def _service_info(order) -> dict | None:
    svc = order.service if order.service_id else None
    if svc is None:
        return None
    return {"id": svc.id, "panel_username": svc.panel_username, "status": svc.status,
            "panel": getattr(svc.panel, "name", "") if svc.panel_id else ""}


def preview(p: Payment) -> dict:
    """What the delete dialog shows: the linked order / service and the allowed choices."""
    o = p.order
    svc = _service_info(o)
    return {
        "id": p.id, "tx_number": p.tx_number, "amount": p.amount, "status": p.status,
        "voided": p.voided_at is not None,
        "order": {"id": o.id, "status": o.status, "type": o.type, "user": o.user.username,
                  "account_name": o.requested_account_name or ""},
        "service": svc,
        "pending": p.status == PaymentStatus.PENDING,
        "actions": [VoidServiceAction.KEEP] + ([VoidServiceAction.DISABLE, VoidServiceAction.DELETE] if svc else []),
        "default_action": VoidServiceAction.KEEP,
        "restore_days": VOID_RESTORE_DAYS,
    }


class _Lock:
    def __init__(self, pk):
        self.key = f"payments:void:lock:{pk}"

    def __enter__(self):
        if not cache.add(self.key, 1, 120):
            raise VoidError("this transaction is being changed — try again in a moment", "busy")
        return self

    def __exit__(self, *exc):
        cache.delete(self.key)


def _panel_step(order, action: str, staff) -> dict:
    """Panel first (disable / delete), then our rows mirror it. Raises VoidError on failure
    so nothing is voided when PasarGuard refused."""
    from apps.panel.exceptions import PanelError
    from apps.panel.services import delete_service, disable_service_on_panel

    svc = order.service if order.service_id else None
    if svc is None or action not in CANCELLING:
        return {}
    info = _service_info(order)
    try:
        if action == VoidServiceAction.DISABLE:
            res = disable_service_on_panel(svc)
            write_audit(action="service.status_changed", staff=staff, target=svc,
                        detail={"status": "disabled", "why": "transaction deleted"})
            return {"service": info, "panel_result": res}
        with transaction.atomic():
            delete_service(svc.id, staff=staff)
        return {"service": info, "panel_result": "deleted"}
    except PanelError as exc:
        raise VoidError(f"PasarGuard refused: {exc} — nothing was deleted", "panel_error") from exc


def void_payment(payment_id: int, *, staff, reason: str, service_action: str = VoidServiceAction.KEEP) -> Payment:
    from apps.orders.models import Order, OrderStatus, ScheduledRenewal

    require_superadmin(staff)
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise VoidError("a reason is required", "invalid", "reason")
    service_action = service_action or VoidServiceAction.KEEP
    if service_action not in VoidServiceAction.values:
        raise VoidError("unknown choice for the order / service", "invalid", "service_action")
    p0 = Payment.objects.select_related("order", "order__service", "order__service__panel").filter(pk=payment_id).first()
    if p0 is None:
        raise VoidError("transaction not found", "not_found")
    if p0.voided_at is not None:
        raise VoidError("this transaction is already deleted", "already")
    if service_action in CANCELLING and not p0.order.service_id:
        raise VoidError("this order has no service to disable or delete", "invalid", "service_action")

    with _Lock(p0.pk):
        panel = _panel_step(p0.order, service_action, staff)
        with transaction.atomic():
            p = Payment.objects.select_for_update().get(pk=p0.pk)
            if p.voided_at is not None:
                raise VoidError("this transaction is already deleted", "already")
            order = Order.objects.select_for_update().get(pk=p.order_id)
            cancel = service_action in CANCELLING or p.status == PaymentStatus.PENDING
            dropped_renewal = None
            prev = ""
            if cancel and order.status != OrderStatus.CANCELLED:
                prev = order.status
                order.status = OrderStatus.CANCELLED
                order.sync_unique_lock()            # releases a still-reserved unique amount
                order.save(update_fields=["status", "amount_unique_lock", "updated_at"])
                sr = ScheduledRenewal.objects.filter(order=order, applied_at__isnull=True).first()
                if sr is not None:
                    dropped_renewal = sr.id
                    sr.delete()
            p.voided_at = timezone.now()
            p.voided_by = staff
            p.void_reason = reason[:255]
            p.void_service_action = service_action
            p.void_prev_order_status = prev
            p.save(update_fields=["voided_at", "voided_by", "void_reason", "void_service_action",
                                  "void_prev_order_status", "updated_at"])
            write_audit(action="payment.voided", staff=staff, target=p, detail={
                "tx": p.tx_number, "amount": str(p.amount), "status": p.status, "reason": p.void_reason,
                "order": order.id, "service_action": service_action, "order_cancelled": bool(prev),
                "order_prev_status": prev, "dropped_scheduled_renewal": dropped_renewal, **panel})
            push_payments_event("payment_voided", order_id=order.id, payment_id=p.id,
                                by=getattr(staff, "username", None))
    return p


def restore_payment(payment_id: int, *, staff) -> Payment:
    from apps.orders.models import Order, OrderStatus

    require_superadmin(staff)
    with transaction.atomic():
        p = Payment.objects.select_for_update().filter(pk=payment_id).first()
        if p is None:
            raise VoidError("transaction not found", "not_found")
        if p.voided_at is None:
            raise VoidError("this transaction is not deleted", "not_voided")
        if not can_restore(p):
            raise VoidError(f"deleted more than {VOID_RESTORE_DAYS} days ago — it can no longer be restored", "expired")
        order = Order.objects.select_for_update().get(pk=p.order_id)
        prev = p.void_prev_order_status
        restored_status = None
        if prev and order.status == OrderStatus.CANCELLED:
            target = prev
            if prev == OrderStatus.PENDING_PAYMENT and (not order.unique_expire_at or order.unique_expire_at <= timezone.now()):
                target = OrderStatus.EXPIRED
            order.status = target
            order.sync_unique_lock()
            try:
                with transaction.atomic():
                    order.save(update_fields=["status", "amount_unique_lock", "updated_at"])
            except IntegrityError:
                # the unique amount was taken by a newer order meanwhile
                order.status = OrderStatus.EXPIRED
                order.sync_unique_lock()
                order.save(update_fields=["status", "amount_unique_lock", "updated_at"])
            restored_status = order.status
        detail = {"tx": p.tx_number, "amount": str(p.amount), "status": p.status, "reason": p.void_reason,
                  "voided_at": p.voided_at.isoformat(), "voided_by": p.voided_by.username if p.voided_by_id else None,
                  "order": order.id, "service_action": p.void_service_action, "order_status": restored_status}
        p.voided_at = None
        p.voided_by = None
        p.void_reason = ""
        p.void_service_action = ""
        p.void_prev_order_status = ""
        p.save(update_fields=["voided_at", "voided_by", "void_reason", "void_service_action",
                              "void_prev_order_status", "updated_at"])
        write_audit(action="payment.restored", staff=staff, target=p, detail=detail)
        push_payments_event("payment_restored", order_id=order.id, payment_id=p.id,
                            by=getattr(staff, "username", None))
    return p
