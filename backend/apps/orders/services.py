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


NAME_TAKEN = "that account name is already taken — pick another"


def check_account_name(panel, name: str) -> None:
    """A new service's account name must be free in our DB *and* on the panel
    (a reseller's customer may already use it there — we never attach to it)."""
    from apps.panel.models import Service
    from apps.panel.services import name_taken_on_panel

    if Service.objects.filter(panel=panel, panel_username__iexact=name).exists():
        raise OrderError(NAME_TAKEN)
    if panel is not None and name_taken_on_panel(panel, name) is not None:
        raise OrderError(NAME_TAKEN)


def rename_paid_order(order: Order, name: str) -> Order:
    """The customer's new account name for a paid order whose first name was
    taken on the panel; fulfilment runs again with it."""
    import re

    name = (name or "").strip()
    if not (order.status == OrderStatus.PAID and order.needs_new_name and order.type == OrderType.NEW):
        raise OrderError("this order does not need a new account name")
    if not re.fullmatch(r"[A-Za-z0-9_.\-]{2,64}", name):
        raise OrderError("use 2–64 English letters, digits, _ . -")
    check_account_name(order.plan.panel, name)
    order.requested_account_name, order.needs_new_name = name, False
    order.save(update_fields=["requested_account_name", "needs_new_name", "updated_at"])
    write_audit(action="order.account_name_changed", target=order, detail={"name": name})
    from .tasks import fulfill_order

    transaction.on_commit(lambda: fulfill_order.delay(order.id))
    return order


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
    discount_code: str | None = None,
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
        check_account_name(plan.panel, name)
        requested_account_name = name

    # --- amount ---
    amount, custom_volume_gb = base_amount(plan, custom_volume_gb)
    original_amount = amount
    discount_amount = Decimal(0)
    dc = None
    if discount_code:
        # discount code (apps.crm.discounts): taken off BEFORE the unique amount is added,
        # so SMS matching / card review always compare against the final price
        quote = _discount_quote(discount_code, user=user, plan=plan, order_type=order_type, amount=amount)
        dc, discount_amount = quote.code, quote.discount
        amount = quote.final

    # A customer who leaves the invoice (e.g. switches to the bank app) and
    # submits the same purchase again must get the SAME order and unique
    # amount back — a second reservation would leave them paying one amount
    # while the SMS matcher approves another.
    existing = _reusable_pending_order(
        user=user, plan=plan, order_type=order_type, service=service,
        requested_account_name=requested_account_name, custom_volume_gb=custom_volume_gb,
    )
    if existing is not None and existing.discount_code_id != (dc.id if dc else None) and not hasattr(existing, "payment"):
        _drop_reservation(existing)          # same purchase, other / no code: a fresh invoice with the new price
        existing = None
    if existing is not None:
        existing.reused = True
        return existing

    order = Order(
        user=user, plan=plan, service=service, type=order_type,
        requested_account_name=requested_account_name if order_type == OrderType.NEW else None,
        custom_volume_gb=custom_volume_gb,
        amount=amount, discount_amount=discount_amount, original_amount=original_amount,
        discount_code=dc, discount_code_text=dc.code if dc else "", status=OrderStatus.PENDING_PAYMENT,
        unique_expire_at=_reservation_deadline(), source=source,
    )
    _assign_unique_amount(order, amount)
    if dc is not None:
        # one code, one open unpaid invoice per customer: buying again replaces it
        for old in Order.objects.select_for_update().filter(user=user, discount_code=dc, status=OrderStatus.PENDING_PAYMENT,
                                                            payment__isnull=True).exclude(pk=order.pk):
            _drop_reservation(old)
        if dc.kind == "winback":
            dc.order = order                  # v1.20: used_at is set when this order is paid
            dc.save(update_fields=["order"])
    order.reused = False
    write_audit(action="order.created", target=order, detail={
        "amount": str(amount), **({"discount_code": dc.code, "discount": str(discount_amount),
                                   "original": str(original_amount)} if dc else {})})
    from apps.notifications.live import push_payments_event

    push_payments_event("order_created", order_id=order.id)
    return order


def base_amount(plan, custom_volume_gb=None) -> tuple[Decimal, int | None]:
    """Plan price for this purchase (plan discount included), before any discount code."""
    if plan.type == PlanType.CUSTOM_VOLUME:
        gb = int(custom_volume_gb or 0)
        lo, hi = plan.min_gb or 1, plan.max_gb or 0
        if gb < lo or (hi and gb > hi):
            raise OrderError(f"custom volume must be between {lo} and {hi} GB")
        return Decimal(plan.price_for_volume(gb)), gb
    return Decimal(plan.final_price), None


class DiscountCodeRefused(OrderError):
    """A discount code that cannot be used — carries the reason in Persian and English."""

    def __init__(self, err):
        self.code, self.fa, self.en = err.code, err.fa, err.en
        super().__init__(err.en)

    def message(self, lang="fa"):
        return self.en if lang == "en" else self.fa


def _discount_quote(raw, *, user, plan, order_type, amount):
    from apps.crm.discounts import DiscountError, evaluate

    try:
        return evaluate(raw, user=user, plan=plan, order_type=order_type, amount=amount)
    except DiscountError as exc:
        raise DiscountCodeRefused(exc) from exc


def quote_order(*, user, plan_id, order_type=OrderType.NEW, custom_volume_gb=None, service_id=None,
                discount_code=None) -> dict:
    """What the customer will pay (shown before the order is made): original, discount,
    final. The unique surcharge is added only when the order is created."""
    plan = Plan.objects.filter(pk=plan_id, is_active=True).first()
    if not plan:
        raise OrderError("plan not found or inactive")
    if order_type in (OrderType.RENEW, OrderType.ADDON_VOLUME):
        from apps.panel.models import Service

        if not Service.objects.filter(pk=service_id, user=user).exists():
            raise OrderError("service not found")
    amount, _ = base_amount(plan, custom_volume_gb)
    out = {"original": amount, "discount": Decimal(0), "final": amount, "code": "", "percent": None}
    if discount_code:
        q = _discount_quote(discount_code, user=user, plan=plan, order_type=order_type, amount=amount)
        out.update(discount=q.discount, final=q.final, code=q.code.code,
                   percent=q.code.percent if q.code.discount_type == "percent" else None)
    return out


def _drop_reservation(order: Order) -> None:
    order.status = OrderStatus.EXPIRED
    order.sync_unique_lock()
    order.save(update_fields=["status", "amount_unique_lock", "updated_at"])


def _reusable_pending_order(*, user, plan, order_type, service, requested_account_name, custom_volume_gb):
    """The customer's still-reserved pending order for exactly this purchase, if any.
    Only a truly open reservation qualifies: pending_payment, not expired, and no
    rejected (or approved) payment on it. Rejected / expired / completed orders
    are never handed back — buying again creates a new order + unique amount."""
    qs = Order.objects.select_for_update().filter(
        user=user, plan=plan, type=order_type, service=service,
        status=OrderStatus.PENDING_PAYMENT, unique_expire_at__gt=timezone.now(),
        custom_volume_gb=custom_volume_gb,
    ).exclude(payment__status__in=[PaymentStatus.REJECTED, PaymentStatus.APPROVED])
    if order_type == OrderType.NEW:
        qs = qs.filter(requested_account_name__iexact=requested_account_name)
    return qs.order_by("-created_at").first()


def _assign_unique_amount(order: Order, base: Decimal) -> None:
    # never hand a customer an amount one of their own recent (rejected /
    # expired) orders had: a late bank SMS for that old payment must not
    # confirm the new order
    from datetime import timedelta

    recent = set(
        Order.objects.filter(user=order.user, created_at__gte=timezone.now() - timedelta(hours=24))
        .values_list("amount_unique", flat=True)
    )
    for surcharge in _surcharge_range():
        candidate = base + Decimal(surcharge)
        if candidate in recent:
            continue
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
    try:
        with transaction.atomic():
            order.save(update_fields=["status", "amount_unique_lock", "updated_at"])
    except IntegrityError:
        # a late approval (order was rejected/expired, its unique amount released
        # and since taken by another open order): pay it without the lock
        order.amount_unique_lock = None
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
