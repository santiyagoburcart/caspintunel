import logging

from celery import shared_task
from django.db import transaction

from apps.common.models import write_audit
from apps.panel.exceptions import PanelError, PanelUnavailable
from apps.panel.models import Panel, Service, ServiceStatus

from .models import Order, OrderStatus, OrderType

log = logging.getLogger("caspintunel")

_RETRY = dict(
    autoretry_for=(PanelUnavailable,),
    retry_backoff=10,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=6,
)


@shared_task
def expire_stale_reservations_task():
    from .services import expire_stale_reservations

    with transaction.atomic():
        return {"expired": expire_stale_reservations()}


@shared_task
def retry_unfulfilled_orders():
    """Re-dispatch fulfilment for orders whose payment was approved but which
    never reached the panel (panel was down / not yet configured / rejected the
    first attempt). Self-heals once the panel is fixed — the operator does not
    have to re-approve anything."""
    from django.utils import timezone

    cutoff = timezone.now() - timezone.timedelta(minutes=2)
    stuck = list(
        Order.objects.filter(status=OrderStatus.PAID, updated_at__lt=cutoff)
        .values_list("id", flat=True)
    )
    for oid in stuck:
        fulfill_order.delay(oid)
    if stuck:
        log.info("retry_unfulfilled_orders: re-dispatched %s", stuck)
    return {"redispatched": len(stuck)}


@shared_task(bind=True, **_RETRY)
def fulfill_order(self, order_id: int):
    """Provision / renew / top-up the service for a paid order (flowchart 1.2 & 1.5)."""
    from apps.panel.services import (
        add_service_data_limit,
        provision_service,
        renew_service,
    )

    order = Order.objects.select_related("plan", "plan__panel", "service").get(pk=order_id)
    if order.status == OrderStatus.COMPLETED:
        return {"already": "completed"}

    try:
        if order.type == OrderType.NEW:
            # multi-panel: the service is created on the plan's own panel
            service = _ensure_service(order, order.plan.panel)
            provision_service(service.id, plan=order.plan)
        elif order.type == OrderType.RENEW:
            renew_service(order.service_id, order.plan)
        elif order.type == OrderType.ADDON_VOLUME:
            add_service_data_limit(order.service_id, int(order.plan.data_limit or 0))
        else:  # pragma: no cover
            raise PanelError(f"unknown order type {order.type}")
    except PanelUnavailable:
        raise
    except PanelError as exc:
        log.error("fulfill_order(%s) permanently failed: %s", order_id, exc)
        write_audit(action="order.fulfillment_failed", target=order, detail={"error": str(exc)})
        raise

    order.refresh_from_db()
    order.status = OrderStatus.COMPLETED
    order.sync_unique_lock()  # releases the amount lock
    order.save(update_fields=["status", "amount_unique_lock", "service", "updated_at"])
    write_audit(action="order.completed", target=order)
    _notify_delivered(order)
    return {"order": order_id, "status": "completed"}


def _notify_delivered(order):
    """Flowchart 1.2: notify the buyer their invoice was approved / service is ready."""
    try:
        from apps.notifications.dispatch import notify_user

        svc = order.service
        link = f"\n\nلینک اشتراک:\n{svc.subscription_url}" if svc and svc.subscription_url else ""
        notify_user(
            order.user,
            title="سرویس شما آماده شد",
            body=f"پرداخت سفارش #{order.id} تأیید و سرویس فعال شد.{link}",
            via_site=True, via_bot=True, via_email=True,
        )
    except Exception as exc:  # noqa: BLE001 - notification must not fail fulfillment
        log.warning("delivery notification for order %s failed: %s", order.id, exc)


def _ensure_service(order: Order, panel: Panel | None) -> Service:
    if order.service_id:
        return order.service
    if panel is None:
        raise PanelError("no active panel configured")

    # custom-volume plans carry no data_limit on the plan — the GB the customer
    # bought lives on the order; bake it onto the service so provisioning sends
    # the right cap (not "unlimited").
    from apps.plans.models import PlanType

    data_limit = int(order.plan.data_limit or 0)
    if order.plan.type == PlanType.CUSTOM_VOLUME and order.custom_volume_gb:
        data_limit = order.plan.data_limit_for_volume(order.custom_volume_gb)

    # username uniqueness is per-panel: the same name may exist on another panel
    existing = Service.objects.filter(
        panel=panel, panel_username=order.requested_account_name
    ).first()
    if existing is not None:
        if existing.user_id != order.user_id:
            # someone else already owns this panel username — do not cross-link
            raise PanelError(
                f"account name '{order.requested_account_name}' is already taken; "
                "reject this order and ask the customer to pick another name"
            )
        service = existing
    else:
        service = Service.objects.create(
            panel_username=order.requested_account_name,
            user=order.user, panel=panel, current_plan=order.plan,
            source=order.source, status=ServiceStatus.PENDING,
            data_limit=data_limit,
        )
    order.service = service
    order.save(update_fields=["service", "updated_at"])
    return service
