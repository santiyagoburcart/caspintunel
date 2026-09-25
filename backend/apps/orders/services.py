"""
Order creation + atomic unique-amount reservation (flowchart 1.2) and
reservation expiry.
"""
from __future__ import annotations

import logging
import random
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.models import write_audit
from apps.payments_sms.models import PaymentStatus
from apps.plans.models import Plan, PlanType
from apps.settings_app.utils import get_setting

from .models import Order, OrderStatus, OrderType

log = logging.getLogger("caspintunel")


class OrderError(Exception):
    """Business-rule violation while creating an order."""


def _reservation_deadline():
    minutes = int(get_setting("unique_amount_reservation_minutes", 30))
    return timezone.now() + timezone.timedelta(minutes=minutes)


def _surcharge_range() -> list[int]:
    lo = int(get_setting("unique_amount_min", 200))
    hi = int(get_setting("unique_amount_max", 1500))
    values = list(range(lo, hi + 1))
    random.shuffle(values)
    return values


def expire_stale_reservations() -> int:
    """
    Move timed-out `pending_payment` orders to `expired` and release their
    unique-amount lock. Orders whose receipt is already awaiting review are
    left alone.
    """
    now = timezone.now()
    stale = (
        Order.objects.filter(status=OrderStatus.PENDING_PAYMENT, unique_expire_at__lt=now)
        .exclude(payment__status=PaymentStatus.PENDING)
    )
    count = 0
    for order in stale.select_for_update():
        order.status = OrderStatus.EXPIRED
        order.sync_unique_lock()
        order.save(update_fields=["status", "amount_unique_lock", "updated_at"])
        count += 1
    if count:
        log.info("expired %s stale order reservation(s)", count)
        from apps.notifications.live import push_payments_event

        push_payments_event("orders_expired", count=count)
    return count


@transaction.atomic
def create_order(
    *,
    user,
    plan_id: int,
    order_type: str = OrderType.NEW,
    requested_account_name: str | None = None,
    custom_volume_gb: int | None = None,
    service_id: int | None = None,
    source: str = "site",
) -> Order:
    expire_stale_reservations()

    plan = Plan.objects.filter(pk=plan_id, is_active=True).select_related("panel").first()
    if not plan:
        raise OrderError("plan not found or inactive")

    service = None
    if order_type in (OrderType.RENEW, OrderType.ADDON_VOLUME):
        from apps.panel.models import Service

        service = Service.objects.filter(pk=service_id, user=user).first()
        if not service:
            raise OrderError("service not found")
        # multi-panel: a renew / top-up plan must live on the same panel as the
        # service (you can't move an account between panels).
        if service.panel_id != plan.panel_id:
            raise OrderError("this plan is on a different panel than the service")
    elif order_type == OrderType.NEW:
        from apps.panel.models import Service

        name = (requested_account_name or "").strip()
        if not name:
            # every new service needs a customer-chosen username — fixed AND
            # custom-volume. We never auto-generate it.
            raise OrderError("requested_account_name is required for a new service")
        # username uniqueness is scoped to the plan's panel
        if Service.objects.filter(panel=plan.panel, panel_username__iexact=name).exists():
            raise OrderError("that account name is already taken — pick another")
        requested_account_name = name

    # --- amount ---
    if plan.type == PlanType.CUSTOM_VOLUME:
        gb = int(custom_volume_gb or 0)
        lo, hi = plan.min_gb or 1, plan.max_gb or 0
        if gb < lo or (hi and gb > hi):
            raise OrderError(f"custom volume must be between {lo} and {hi} GB")
        amount = plan.price_for_volume(gb)
    else:
        amount = plan.final_price
        custom_volume_gb = None
    amount = Decimal(amount)

    # A customer who leaves the invoice (e.g. switches to the bank app) and
    # submits the same purchase again must get the SAME order and unique
    # amount back — a second reservation would leave them paying one amount
    # while the SMS matcher approves another.
    existing = _reusable_pending_order(
        user=user, plan=plan, order_type=order_type, service=service,
        requested_account_name=requested_account_name, custom_volume_gb=custom_volume_gb,
    )
    if existing is not None:
        existing.reused = True
        return existing

    order = Order(
        user=user, plan=plan, service=service, type=order_type,
        requested_account_name=requested_account_name if order_type == OrderType.NEW else None,
        custom_volume_gb=custom_volume_gb,
        amount=amount, status=OrderStatus.PENDING_PAYMENT,
        unique_expire_at=_reservation_deadline(), source=source,
    )
    _assign_unique_amount(order, amount)
    order.reused = False
    write_audit(action="order.created", target=order, detail={"amount": str(amount)})
    from apps.notifications.live import push_payments_event

    push_payments_event("order_created", order_id=order.id)
    return order


def _reusable_pending_order(*, user, plan, order_type, service, requested_account_name, custom_volume_gb):
    """The customer's still-reserved pending order for exactly this purchase, if any."""
    qs = Order.objects.select_for_update().filter(
        user=user, plan=plan, type=order_type, service=service,
        status=OrderStatus.PENDING_PAYMENT, unique_expire_at__gt=timezone.now(),
        custom_volume_gb=custom_volume_gb,
    )
    if order_type == OrderType.NEW:
        qs = qs.filter(requested_account_name__iexact=requested_account_name)
    return qs.order_by("-created_at").first()


def _assign_unique_amount(order: Order, base: Decimal) -> None:
    for surcharge in _surcharge_range():
        candidate = base + Decimal(surcharge)
        order.amount_unique = candidate
        order.amount_unique_lock = candidate
        try:
            with transaction.atomic():
                order.save()
            return
        except IntegrityError:
            continue
    raise OrderError("could not allocate a unique amount right now, please retry")


def mark_paid_and_fulfill(order: Order) -> None:
    """Called after a payment is approved."""
    from .tasks import fulfill_order

    order.status = OrderStatus.PAID
    order.sync_unique_lock()  # PAID still holds the lock until provisioning completes
    order.save(update_fields=["status", "amount_unique_lock", "updated_at"])
    transaction.on_commit(lambda: fulfill_order.delay(order.id))


def schedule_renewal(order: Order) -> ScheduledRenewal:
    """A paid 'renew' order doesn't touch the panel right away — it just
    records what to apply once the service actually reaches the end of its
    current cycle (see apps.panel.tasks.apply_due_scheduled_renewals).
    renewal_mode/carry_over_data are copied from the plan at this moment so a
    later plan edit can never change how an already-paid renewal is applied."""
    from .models import ScheduledRenewal

    plan = order.plan
    renewal, _created = ScheduledRenewal.objects.update_or_create(
        service_id=order.service_id,
        defaults={
            "plan": plan,
            "order": order,
            "renewal_mode": plan.renewal_mode,
            "carry_over_data": plan.carry_over_data,
            "applied_at": None,
        },
    )
    write_audit(action="renewal.scheduled", target=order, detail={"plan": plan.id})
    return renewal
