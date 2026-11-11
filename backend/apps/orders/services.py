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


class AccountNameRefused(OrderError):
    """The account name breaks PasarGuard's username rule (apps/panel/account_names.py) — refused BEFORE payment.
    Carries the reason in Persian and English and a fixed suggestion."""

    def __init__(self, err):
        self.err, self.code, self.suggestion = err, err.code, err.suggestion
        super().__init__(err.message("en"))

    def message(self, lang="fa", *, with_suggestion=False):
        return self.err.message(lang, with_suggestion=with_suggestion)


def clean_account_name(name) -> str:
    """The name PasarGuard will accept (stripped) or AccountNameRefused."""
    from apps.panel.account_names import AccountNameInvalid, validate

    try:
        return validate(name)
    except AccountNameInvalid as exc:
        raise AccountNameRefused(exc) from exc


class RenewalWaiting(OrderError):
    """This service already has a renewal that is paid (or whose receipt is being
    reviewed) and not applied yet — a second one is refused (incident 2026-10-29,
    order #30: a customer paid one renewal and was charged for two)."""

    code = "renewal_waiting"

    def __init__(self, waiting: dict):
        self.waiting = waiting
        if waiting["state"] == "review":
            self.fa = "رسید پرداخت تمدید این سرویس در حال بررسی است؛ تا نتیجه‌ی آن نمی‌توانید دوباره تمدید کنید."
            self.en = "A renewal payment for this service is being reviewed; you can't renew again until it is decided."
        else:
            self.fa = "تمدید این سرویس پرداخت شده و در انتظار اعمال است — با پایان حجم/زمان فعلی اعمال می‌شود."
            self.en = "A renewal for this service is already paid and waiting — it applies when the current volume/time ends."
        super().__init__(self.en)

    def message(self, lang="fa"):
        return self.en if lang == "en" else self.fa


class RenewalConflict(Exception):
    """A paid renewal order found another, still unapplied renewal on its service.
    The waiting one is never overwritten; staff are alerted instead."""

    def __init__(self, waiting_order_id: int):
        self.waiting_order_id = waiting_order_id
        super().__init__(f"service already has a waiting renewal (order #{waiting_order_id})")


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


def retry_provision(order: Order, staff, account_name: str | None = None) -> Order:
    """v1.42.1 «ساخت ناموفق» → «تلاش دوباره» (staff): optionally a new account name (PasarGuard's rule + free in our
    DB and on the panel), then the failure is cleared and fulfilment runs again. Only for a PAID order that never
    reached the panel; the service row is renamed only while it has no panel account (no subscription link)."""
    order = Order.objects.select_for_update().select_related("plan__panel", "service").get(pk=order.pk)
    if order.status != OrderStatus.PAID:
        raise OrderError("only a paid order that was not delivered can be retried")
    detail = {"previous_error": order.provision_error}
    name = (account_name or "").strip()
    if name and order.type == OrderType.NEW and name != (order.requested_account_name or ""):
        name = clean_account_name(name)
        svc = order.service
        if svc is not None and svc.subscription_url:
            raise OrderError("this service already exists on the panel — its name can't be changed here")
        check_account_name(order.plan.panel, name)
        detail.update({"from": order.requested_account_name, "to": name})
        order.requested_account_name = name
        if svc is not None:
            from apps.panel.models import ServiceStatus

            svc.panel_username, svc.status = name, ServiceStatus.PENDING
            svc.save(update_fields=["panel_username", "status", "updated_at"])
    order.provision_error, order.provision_failed_at, order.needs_new_name = "", None, False
    order.save(update_fields=["requested_account_name", "provision_error", "provision_failed_at", "needs_new_name",
                              "updated_at"])
    write_audit(action="order.provision_retry", staff=staff, target=order, detail=detail)
    from django.core.cache import cache

    cache.delete_many([f"provfail:{order.id}", f"provfail-p:{order.id}"])   # a new failure alerts again (store + us)
    from apps.tenancy import context as tctx

    from .tasks import fulfill_order

    tid = tctx.current_tenant_id()           # v1.52.1: our staff retry a store's order from «فروشگاه» — queue it in THAT store

    def _queue():
        with tctx.tenant_context(tid):
            fulfill_order.delay(order.id)

    transaction.on_commit(_queue if tid else (lambda: fulfill_order.delay(order.id)))
    return order


def rename_paid_order(order: Order, name: str) -> Order:
    """The customer's new account name for a paid order whose first name was
    taken on the panel; fulfilment runs again with it."""
    if not (order.status == OrderStatus.PAID and order.needs_new_name and order.type == OrderType.NEW):
        raise OrderError("this order does not need a new account name")
    name = clean_account_name(name)
    check_account_name(order.plan.panel, name)
    order.requested_account_name, order.needs_new_name = name, False
    order.save(update_fields=["requested_account_name", "needs_new_name", "updated_at"])
    write_audit(action="order.account_name_changed", target=order, detail={"name": name})
    from .tasks import fulfill_order

    transaction.on_commit(lambda: fulfill_order.delay(order.id))
    return order


def _order_plan(user, plan_id, order_type, service_id):
    """(plan, service) for a new order / quote. A renewal may use any active plan of the service's panel (fixed or
    custom volume) or the service's own plan when it is inactive but staff marked it renewable."""
    plan = Plan.objects.filter(pk=plan_id).select_related("panel").first()
    service = None
    if order_type in (OrderType.RENEW, OrderType.ADDON_VOLUME):
        from apps.panel.models import Service

        service = Service.objects.filter(pk=service_id, user=user).first()
        if not service:
            raise OrderError("service not found")
        if plan is not None and order_type == OrderType.RENEW and not plan_renews(service, plan):
            raise OrderError("this plan cannot be used to renew this service")
        # multi-panel: a renew / top-up plan must live on the same panel as the service
        if plan is not None and service.panel_id != plan.panel_id:
            raise OrderError("this plan is on a different panel than the service")
    if plan is None or not (plan.is_active or (order_type == OrderType.RENEW and plan_renews(service, plan))):
        raise OrderError("plan not found or inactive")
    return plan, service


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

    plan, service = _order_plan(user, plan_id, order_type, service_id)
    if order_type in (OrderType.RENEW, OrderType.ADDON_VOLUME):
        from apps.panel.models import Service

        if order_type == OrderType.RENEW:
            # one renewal at a time: lock the service row so two quick taps can't both pass
            Service.objects.select_for_update().filter(pk=service.pk).first()
            waiting = waiting_renewal(service)
            if waiting is not None:
                raise RenewalWaiting(waiting)
    elif order_type == OrderType.NEW:
        # every new service needs a customer-chosen username — fixed AND custom-volume (never auto-generated) —
        # in PasarGuard's format, checked before payment (a 422 after payment left a paid order without a service)
        name = clean_account_name(requested_account_name)
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

    quota_guard(plan, custom_volume_gb)          # v1.46: a store's reseller must have the volume (never our own store)
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
        if dc.kind in ("winback", "credit"):      # personal one-use codes (v1.56: + carried-over credit)
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


class SaleUnavailable(OrderError):
    """v1.46 (multi-tenant Phase 4): the store's reseller quota cannot cover this purchase (tenancy/quota.py)."""

    code = "quota"

    def __init__(self, exc):
        self.fa, self.en = exc.fa, getattr(exc, "en_customer", None) or _QUOTA_EN
        super().__init__(self.fa)

    def message(self, lang="fa"):
        return self.en if lang == "en" else self.fa


def quota_guard(plan, custom_volume_gb=None) -> None:
    """Store sales only (our own store is never checked): raises SaleUnavailable."""
    from apps.tenancy import quota

    try:
        quota.check(quota.plan_bytes(plan, custom_volume_gb))
    except quota.QuotaShort as exc:
        raise SaleUnavailable(exc) from exc


_QUOTA_EN = "This purchase is temporarily unavailable — please try again a little later or contact support."


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
    plan, service = _order_plan(user, plan_id, order_type, service_id)
    if order_type in (OrderType.RENEW, OrderType.ADDON_VOLUME):
        if order_type == OrderType.RENEW:
            waiting = waiting_renewal(service)
            if waiting is not None:
                raise RenewalWaiting(waiting)
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
    # v1.34: one pool with agency payments (apps/agency/billing.py) — skip what they hold. v1.47: only OUR store shares
    # that pool; a reseller store has its own (its SMS devices are its own)
    from apps.agency.billing import agency_locked_amounts
    from apps.tenancy.context import store_id

    agency_held = set() if store_id() else agency_locked_amounts()
    for surcharge in _surcharge_range():
        candidate = base + Decimal(surcharge)
        if candidate in recent or candidate in agency_held:
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

    if order.manual_invoice_id:
        # v1.38 «فاکتور دستی»: the invoice is paid; no unique-amount lock; without a service action
        # (type manual) there is nothing to deliver — the order is completed here
        from .manual import on_order_paid

        on_order_paid(order)
        if order.type == OrderType.MANUAL:
            order.status = OrderStatus.COMPLETED
            order.amount_unique_lock = None
            order.save(update_fields=["status", "amount_unique_lock", "updated_at"])
            write_audit(action="order.completed", target=order, detail={"manual_invoice": order.manual_invoice_id})
            return
        order.status = OrderStatus.PAID
        order.amount_unique_lock = None
        order.save(update_fields=["status", "amount_unique_lock", "updated_at"])
        transaction.on_commit(lambda: fulfill_order.delay(order.id))
        return
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


def renewal_plans(service):
    """Plans a service can switch / upgrade to on renewal: every active plan of the service's panel, fixed or custom
    volume («حجم دلخواه»). A renewal always runs on the SAME PasarGuard account (username + subscription link)."""
    return Plan.objects.filter(is_active=True, panel_id=service.panel_id).order_by("sort_order", "price", "id")


def plan_renews(service, plan) -> bool:
    """`plan` may renew `service`: an active plan of its panel, or the service's own plan when that was retired
    (inactive) and staff ticked «قابل تمدید با وجود غیرفعال بودن» (Plan.renewable_when_inactive)."""
    if service is None or plan is None or plan.panel_id != service.panel_id:
        return False
    if plan.is_active:
        return True
    return plan.pk == service.current_plan_id and bool(plan.renewable_when_inactive)


def last_renewal_gb(service, plan=None) -> int | None:
    """The volume (GB) to pre-fill for a custom-volume renewal: the last one bought for this service, else its current
    volume; kept inside the plan's min / max."""
    o = (Order.objects.filter(service_id=service.pk, custom_volume_gb__isnull=False,
                              status__in=(OrderStatus.PAID, OrderStatus.COMPLETED)).order_by("-id").first())
    gb = o.custom_volume_gb if o else (round(service.data_limit / 1024 ** 3) if service.data_limit else None)
    if gb is None or plan is None:
        return gb
    lo, hi = plan.min_gb or 1, plan.max_gb or 0
    return max(lo, min(gb, hi)) if hi else max(lo, gb)


def waiting_renewal(service) -> dict | None:
    """The renewal of this service that is paid (or under receipt review) but not applied
    yet, as {"state": "paid" | "review", "order": Order, "plan": Plan} — else None.
    "paid": queued (ScheduledRenewal) or paid and about to be queued. "review": a receipt /
    SMS-mismatch payment for a renewal order still waits for staff."""
    from .models import ScheduledRenewal

    sr = (ScheduledRenewal.objects.filter(service_id=service.pk, applied_at__isnull=True)
          .select_related("plan", "order").first())
    if sr is not None:
        return {"state": "paid", "order": sr.order, "plan": sr.plan}
    base = Order.objects.filter(service_id=service.pk, type=OrderType.RENEW).select_related("plan").order_by("-id")
    o = base.filter(status=OrderStatus.PAID).first()
    if o is not None:
        return {"state": "paid", "order": o, "plan": o.plan}
    o = base.filter(status=OrderStatus.PENDING_PAYMENT, payment__status=PaymentStatus.PENDING,
                    payment__voided_at__isnull=True).first()
    if o is not None:
        return {"state": "review", "order": o, "plan": o.plan}
    return None


def pending_renewal_info(service) -> dict | None:
    """waiting_renewal() as plain data for the site / Mini App (service card, renew-info).
    It applies when the current volume runs out or at `applies_by` (the current expiry),
    whichever comes first."""
    w = waiting_renewal(service)
    if w is None:
        return None
    plan = w["plan"]
    return {
        "state": w["state"],
        "order_id": w["order"].id,
        "plan_id": plan.id if plan else None,
        "plan_name": plan.name_fa if plan else None,
        "plan_name_en": (plan.name_en or plan.name_fa) if plan else None,
        "data_limit": plan.data_limit if plan else None,
        "duration_days": plan.duration_days if plan else None,
        "applies_by": service.expire_at,
    }


def renewable_plan(service):
    """The service's own plan when it can be bought again for a renewal (one tap), else None: no plan, another
    panel's plan, or a retired plan staff did not mark renewable — the customer then picks from the plan list."""
    plan = service.current_plan
    return plan if plan_renews(service, plan) else None


def schedule_renewal(order: Order) -> ScheduledRenewal:
    """A paid 'renew' order doesn't touch the panel right away — it just
    records what to apply once the service actually reaches the end of its
    current cycle (see apps.panel.tasks.apply_due_scheduled_renewals).
    renewal_mode/carry_over_data are copied from the plan at this moment so a
    later plan edit can never change how an already-paid renewal is applied."""
    from .models import ScheduledRenewal

    plan = order.plan
    # a custom-volume renewal carries the GB the customer bought (the plan itself has no fixed volume)
    data_limit = (plan.data_limit_for_volume(order.custom_volume_gb)
                  if plan.type == PlanType.CUSTOM_VOLUME and order.custom_volume_gb else None)
    fields = {"plan": plan, "order": order, "renewal_mode": plan.renewal_mode,
              "carry_over_data": plan.carry_over_data, "data_limit": data_limit, "applied_at": None}
    with transaction.atomic():
        renewal = ScheduledRenewal.objects.select_for_update().filter(service_id=order.service_id).first()
        if renewal is not None and renewal.applied_at is None and renewal.order_id != order.id:
            # another paid renewal still waits: never replace it (that silently dropped a paid renewal)
            raise RenewalConflict(renewal.order_id)
        if renewal is None:
            renewal = ScheduledRenewal.objects.create(service_id=order.service_id, **fields)
        else:   # the row of an already applied renewal (one per service), or a retry of this order
            for k, v in fields.items():
                setattr(renewal, k, v)
            renewal.save()
    write_audit(action="renewal.scheduled", target=order, detail={"plan": plan.id})
    # the customer paid for this plan: it is the service's plan from now on (the next
    # one-tap renewal offers it); the renewal itself is applied by the scheduled job
    service = order.service
    if service is not None and service.current_plan_id != plan.id:
        old = service.current_plan_id
        service.current_plan = plan
        service.save(update_fields=["current_plan", "updated_at"])
        write_audit(action="service.plan_changed", target=service,
                    detail={"old_plan": old, "plan": plan.id, "order": order.id, "via": "renewal"})
    return renewal
