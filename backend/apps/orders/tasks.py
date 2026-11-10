import logging

from celery import shared_task
from django.db import transaction

from apps.common.models import write_audit
from apps.panel.exceptions import PanelError, PanelNameTaken, PanelUnavailable
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

    from apps.agency.billing import expire_stale
    from apps.tenancy.context import for_each_tenant

    def one_store():
        with transaction.atomic():
            return expire_stale_reservations()

    per = for_each_tenant(one_store, name="expire_stale_reservations")      # v1.46: every store's checkouts
    out = {"expired": sum(v for v in per.values() if isinstance(v, int))}
    with transaction.atomic():
        out["agency_expired"] = expire_stale()     # v1.34 unfinished agency checkouts
    return out


@shared_task
def retry_unfulfilled_orders():
    """Re-dispatch fulfilment for orders whose payment was approved but which
    never reached the panel (panel was down / not yet configured / rejected the
    first attempt). Self-heals once the panel is fixed — the operator does not
    have to re-approve anything."""
    from django.utils import timezone

    from apps.tenancy.context import for_each_tenant

    def one_store():
        cutoff = timezone.now() - timezone.timedelta(minutes=2)
        stuck = list(
            Order.objects.filter(status=OrderStatus.PAID, updated_at__lt=cutoff, needs_new_name=False,
                                 provision_failed_at__isnull=True)    # «ساخت ناموفق»: staff fix it, no retry loop
            .values_list("id", flat=True)
        )
        for oid in stuck:
            fulfill_order.delay(oid)                     # queued inside the store's context → runs for that store
        if stuck:
            log.info("retry_unfulfilled_orders: re-dispatched %s", stuck)
        return len(stuck)

    per = for_each_tenant(one_store, name="retry_unfulfilled_orders")      # v1.46: every store
    return {"redispatched": sum(v for v in per.values() if isinstance(v, int))}


@shared_task(bind=True, **_RETRY)
def fulfill_order(self, order_id: int):
    """Provision / schedule-renew / top-up the service for a paid order
    (flowchart 1.2 & 1.5). A 'renew' order no longer touches the panel here —
    it's deferred to apply_due_scheduled_renewals once the service actually
    reaches the end of its current cycle, so an early renewal doesn't discard
    time/volume the customer already paid for."""
    from apps.panel.services import add_service_data_limit, provision_service

    from .services import RenewalConflict, schedule_renewal

    order = Order.objects.select_related("plan", "plan__panel", "service").get(pk=order_id)
    if order.status == OrderStatus.COMPLETED:
        return {"already": "completed"}
    if order.status == OrderStatus.CANCELLED:
        # its payment was deleted (voided) with "cancel the order" — never deliver it
        return {"skipped": "cancelled"}

    if order.type in (OrderType.NEW, OrderType.ADDON_VOLUME):
        # v1.46 (multi-tenant Phase 4): a store's reseller must still have the volume right before the account is made
        from apps.tenancy import quota

        try:
            quota.check_order(order)
        except quota.QuotaShort as exc:
            return _quota_wait(order, exc)

    try:
        if order.type == OrderType.NEW:
            # multi-panel: the service is created on the plan's own panel
            service = _ensure_service(order, order.plan.panel)
            provision_service(service.id, plan=order.plan)
        elif order.type == OrderType.RENEW:
            schedule_renewal(order)
        elif order.type == OrderType.ADDON_VOLUME:
            add_service_data_limit(order.service_id, int(order.plan.data_limit or 0))
        else:  # pragma: no cover
            raise PanelError(f"unknown order type {order.type}")
    except PanelUnavailable:
        raise
    except PanelNameTaken as exc:
        return _ask_for_new_name(order, exc)
    except RenewalConflict as exc:
        return _renewal_conflict(order, exc)
    except PanelError as exc:
        return _provision_failed(order, exc)

    order.refresh_from_db()
    order.provision_error, order.provision_failed_at = "", None
    order.status = OrderStatus.COMPLETED
    order.sync_unique_lock()  # releases the amount lock
    order.save(update_fields=["status", "amount_unique_lock", "service", "provision_error", "provision_failed_at",
                              "updated_at"])
    write_audit(action="order.completed", target=order)
    # a renewal isn't "delivered" yet — apply_scheduled_renewal notifies the
    # user itself once it actually applies the new plan; v1.51.1: at payment the customer is told it is queued
    if order.type != OrderType.RENEW:
        _notify_delivered(order)
    else:
        _notify_renewal_queued(order)
    return {"order": order_id, "status": "completed"}


def _quota_wait(order: Order, exc) -> dict:
    """Paid, but the store's reseller is out of quota: nothing is created; the order stays `paid` and
    retry_unfulfilled_orders tries again every minute — it is delivered as soon as the reseller's quota is raised.
    The reseller (portal notice) and we (staff alert) were told by quota.check, once an hour."""
    log.warning("order %s waits for the store's reseller quota: %s", order.id, exc)
    return {"order": order.id, "waiting": "quota", "detail": str(exc)[:200]}


def panel_error_text(exc) -> str:
    """PasarGuard's own message for a refused request (422 body `detail`), else the exception text."""
    import json

    body = getattr(exc, "body", None)
    if body:
        try:
            detail = json.loads(body).get("detail")
        except (ValueError, AttributeError):
            detail = None
        if isinstance(detail, list):
            detail = "; ".join(str(d.get("msg", d)) if isinstance(d, dict) else str(d) for d in detail)
        if detail:
            return f"{exc} — {detail}"[:1000]
    return str(exc)[:1000]


def _provision_failed(order: Order, exc) -> dict:
    """v1.42.1: paid, but PasarGuard refused the account (not a name clash, not an outage). The order stays `paid`
    with «ساخت ناموفق» (provision_error / provision_failed_at): the retry job skips it, staff get ONE Telegram alert
    with the panel's error and fix the name or retry in the panel, the customer is told ONCE that the service is
    being prepared and support follows up — never a broken service."""
    from django.utils import timezone

    from apps.common.staff_alert import alert_staff

    text = panel_error_text(exc)
    first = order.provision_failed_at is None
    order.provision_error = text
    if first:
        order.provision_failed_at = timezone.now()
    order.save(update_fields=["provision_error", "provision_failed_at", "updated_at"])
    log.error("fulfill_order(%s) failed on the panel: %s", order.id, text)
    write_audit(action="order.fulfillment_failed", target=order, detail={"error": text})
    if not first:
        return {"order": order.id, "status": "provision_failed"}
    payment = getattr(order, "payment", None)
    name = order.requested_account_name or (order.service.panel_username if order.service_id else "-")
    alert_staff(
        "🚨 ساخت سرویس ناموفق / Provisioning failed\n"
        f"Order #{order.id} · {order.user.username} · account «{name}» · "
        f"TX {getattr(payment, 'tx_number', None) or getattr(payment, 'id', '-')} is PAID but PasarGuard refused it:\n"
        f"{text}\n"
        "Panel → Transactions → this payment → «ساخت ناموفق»: edit the account name or «تلاش دوباره».",
        perm="payment.approve", dedupe_key=f"provfail:{order.id}", ttl=86400)
    try:
        from apps.notifications.dispatch import notify_user
        from apps.notifications.models import NotificationType

        notify_user(
            order.user,
            title="سرویس در حال آماده‌سازی است",
            body=f"پرداخت سفارش #{order.id} تأیید شده. سرویس در حال آماده‌سازی است، پشتیبانی پیگیری می‌کند.",
            title_en="Your service is being prepared",
            body_en=f"Order #{order.id} is paid. Your service is being prepared — support is following it up.",
            ntype=NotificationType.ORDER_CONFIRMED, via_site=True, via_bot=True, via_email=False,
        )
    except Exception as e:  # noqa: BLE001 - notification must not fail the task
        log.warning("provisioning-failed notice for order %s not delivered: %s", order.id, e)
    try:
        from apps.notifications.live import push_payments_event

        push_payments_event("provision_failed", order_id=order.id)
    except Exception:  # noqa: BLE001
        pass
    return {"order": order.id, "status": "provision_failed"}


def _renewal_conflict(order: Order, exc) -> dict:
    """A paid renewal whose service already has another paid renewal waiting: the waiting
    one is kept, this order becomes `failed` (never queued twice) and staff decide —
    usually a duplicate payment to void or refund. The customer is told it's being checked."""
    from apps.common.staff_alert import alert_staff

    order.status = OrderStatus.FAILED
    order.sync_unique_lock()
    order.save(update_fields=["status", "amount_unique_lock", "updated_at"])
    payment = getattr(order, "payment", None)
    write_audit(action="renewal.conflict", target=order, detail={
        "service": order.service_id, "waiting_order": exc.waiting_order_id,
        "payment": getattr(payment, "id", None)})
    log.warning("order %s: service %s already has a waiting renewal (order %s) — not queued, staff alerted",
                order.id, order.service_id, exc.waiting_order_id)
    tx = getattr(payment, "tx_number", None) or getattr(payment, "id", "-")
    alert_staff(
        "⚠️ تمدید تکراری / Duplicate renewal\n"
        f"Order #{order.id} ({order.user.username}, service {order.service.panel_username if order.service else '-'}) "
        f"is paid (TX {tx}, {order.amount_unique} T), but order #{exc.waiting_order_id} is already a paid renewal "
        f"waiting for this service.\nThe waiting renewal was kept; #{order.id} was NOT queued (status: failed). "
        "Check Payments — void or refund the duplicate.",
        perm="payment.approve", dedupe_key=f"renewconflict:{order.id}", ttl=86400)
    try:
        from apps.notifications.dispatch import notify_user
        from apps.notifications.models import NotificationType

        notify_user(
            order.user,
            title="پرداخت تمدید در حال بررسی",
            body=(f"پرداخت سفارش #{order.id} ثبت شد، اما برای این سرویس یک تمدید پرداخت‌شده‌ی دیگر در انتظار اعمال است. "
                  "پشتیبانی آن را بررسی می‌کند و با شما تماس می‌گیرد."),
            title_en="Renewal payment under review",
            body_en=(f"The payment for order #{order.id} was received, but this service already has another paid renewal "
                     "waiting. Support will review it and contact you."),
            ntype=NotificationType.ORDER_CONFIRMED, via_site=True, via_bot=True, via_email=True,
        )
    except Exception as exc2:  # noqa: BLE001
        log.warning("renewal conflict notice to user failed: %s", exc2)
    return {"order": order.id, "status": "failed", "conflict_with": exc.waiting_order_id}


def _ask_for_new_name(order: Order, exc: PanelNameTaken) -> dict:
    """Paid, but the name exists on the panel as someone else's account: drop
    our never-provisioned service row, keep the order paid and ask the customer
    (site + bot) for another name. Never attached, never retried by itself."""
    svc = order.service
    with transaction.atomic():
        order.service = None
        order.needs_new_name = True
        order.save(update_fields=["service", "needs_new_name", "updated_at"])
        if svc is not None and not svc.subscription_url and svc.status == ServiceStatus.PENDING \
                and not svc.orders.exclude(pk=order.pk).exists():
            svc.delete()
    write_audit(action="order.account_name_taken", target=order,
                detail={"name": exc.username, "panel_owner": exc.owner or ""})
    log.warning("order %s: account name %s exists on the panel (admin %s) — asked the customer for another",
                order.id, exc.username, exc.owner)
    try:
        from apps.notifications.dispatch import notify_user
        from apps.notifications.models import NotificationType

        notify_user(
            order.user,
            title="نام اکانت را عوض کنید",
            body=(f"پرداخت سفارش #{order.id} تأیید شده، اما نام «{exc.username}» روی سرور قبلاً استفاده شده است. "
                  "لطفاً یک نام دیگر انتخاب کنید تا سرویس ساخته شود."),
            title_en="Choose another account name",
            body_en=(f"Order #{order.id} is paid, but the name “{exc.username}” is already in use on the server. "
                     "Please choose another name and your service will be created."),
            ntype=NotificationType.ORDER_CONFIRMED, via_site=True, via_bot=False, via_email=True,
            link=f"/checkout?order={order.id}",
        )
        _send_bot_rename_prompt(order, exc.username)
    except Exception as e:  # noqa: BLE001 - notification must not fail the task
        log.warning("new-name request for order %s not delivered: %s", order.id, e)
    return {"order": order.id, "status": "needs_new_name"}


def _send_bot_rename_prompt(order, name: str) -> bool:
    user = order.user
    if not user.telegram_id:
        return False
    from apps.telegram.config import sales_client

    client = sales_client()
    if client is None:
        return False
    en = getattr(user, "language", "fa") == "en"
    text = (f"⚠️ Order #{order.id} is paid, but the account name <code>{name}</code> is already in use on the server.\n"
            "Tap the button and send another name — your service is created right away."
            if en else
            f"⚠️ پرداخت سفارش #{order.id} تأیید شده، اما نام <code>{name}</code> روی سرور قبلاً استفاده شده است.\n"
            "دکمه را بزنید و یک نام دیگر بفرستید تا سرویس ساخته شود.")
    kb = {"inline_keyboard": [[{"text": "✏️ Choose another name" if en else "✏️ انتخاب نام جدید",
                                "callback_data": f"nn:{order.id}"}]]}
    client.send_message(user.telegram_id, text, parse_mode="HTML", reply_markup=kb)
    return True


def renewal_queued_text(service, plan, data_limit: int | None) -> dict:
    """v1.51.1 «تمدید پرداخت شد…» for a paid, queued renewal: new plan, volume, days and when it applies (the current
    volume running out or the current expiry, whichever first; a service already expired / out of volume: in a few
    minutes — apply_due_scheduled_renewals runs every 5 min). Latin digits, Tehran time."""
    from apps.common.jalali import to_jalali_str
    from apps.panel.models import ServiceStatus

    limit = int(data_limit or 0) or int(plan.data_limit or 0)
    gb = f"{limit / 1024 ** 3:g}" if limit else ""
    vol_fa, vol_en = (f"{gb} گیگ", f"{gb} GB") if gb else ("نامحدود", "unlimited")
    days = int(plan.duration_days or 0)
    days_fa, days_en = (f" · {days} روز", f" · {days} days") if days else ("", "")
    name_fa, name_en = plan.name_fa, plan.name_en or plan.name_fa
    if service.status in (ServiceStatus.EXPIRED, ServiceStatus.LIMITED):
        when_fa, when_en = "ظرف چند دقیقه (سرویس فعلی تمام شده است).", "within a few minutes (the current service has ended)."
    elif service.expire_at:
        d = to_jalali_str(service.expire_at)
        when_fa = f"با تمام شدن حجم فعلی یا در {d}، هرکدام زودتر."
        when_en = f"when the current volume runs out or on {d} (Tehran time), whichever comes first."
    else:
        when_fa, when_en = "با تمام شدن حجم فعلی.", "when the current volume runs out."
    account = service.panel_username or f"#{service.pk}"
    return {
        "title": "تمدید پرداخت شد — با پایان حجم/زمان فعلی اعمال می‌شود",
        "title_en": "Renewal paid — it applies when the current volume/time ends",
        "body": (f"سرویس: {account}\nپلن تمدید: {name_fa} · {vol_fa}{days_fa}\nاعمال: {when_fa}\n"
                 "تا آن موقع سرویس فعلی بدون تغییر کار می‌کند."),
        "body_en": (f"Service: {account}\nRenewal plan: {name_en} · {vol_en}{days_en}\nApplies: {when_en}\n"
                    "Until then your current service keeps working as it is."),
    }


def _notify_renewal_queued(order):
    """v1.51.1: the customer learns at payment that the renewal is queued (site + bot) — before, nothing was sent until
    it applied, and a paid renewal looked lost (TX-000078). Never blocks fulfilment."""
    try:
        from apps.notifications.dispatch import notify_user
        from apps.notifications.models import NotificationType

        from .models import ScheduledRenewal

        from django.core.cache import cache

        sr = ScheduledRenewal.objects.filter(order=order, applied_at__isnull=True).select_related("plan", "service").first()
        if sr is None or not cache.add(f"renewal_queued_notice:{order.id}", 1, 14 * 86400):   # once per order
            return
        text = renewal_queued_text(sr.service, sr.plan, sr.data_limit)
        notify_user(order.user, ntype=NotificationType.ORDER_CONFIRMED, via_site=True,
                    via_bot=bool(order.user.telegram_id), link="/", **text)
    except Exception as exc:  # noqa: BLE001 - notification must not fail fulfillment
        log.warning("renewal-queued notification for order %s failed: %s", order.id, exc)


def _notify_delivered(order):
    """Flowchart 1.2: notify the buyer their invoice was approved / service is ready.
    Site + email get the text; the bot gets the service card instead — QR code
    with the subscription link as tap-to-copy monospace."""
    try:
        from apps.notifications.dispatch import notify_user
        from apps.notifications.models import NotificationType

        svc = order.service
        link = f"\n\nلینک اشتراک:\n{svc.subscription_url}" if svc and svc.subscription_url else ""
        link_en = f"\n\nSubscription link:\n{svc.subscription_url}" if svc and svc.subscription_url else ""
        notify_user(
            order.user,
            title="سرویس شما آماده شد",
            body=f"پرداخت سفارش #{order.id} تأیید و سرویس فعال شد.{link}",
            title_en="Your service is ready",
            body_en=f"Order #{order.id} was approved and your service is now active.{link_en}",
            ntype=NotificationType.SERVICE_READY,
            via_site=True, via_bot=not (svc and svc.subscription_url), via_email=True,
        )
        if svc and svc.subscription_url:
            _send_bot_service_card(order.user, svc, order)
    except Exception as exc:  # noqa: BLE001 - notification must not fail fulfillment
        log.warning("delivery notification for order %s failed: %s", order.id, exc)


def _send_bot_service_card(user, svc, order) -> bool:
    if not user.telegram_id:
        return False
    try:
        from apps.telegram.config import sales_client
        from apps.telegram.shop import qr_png, service_caption

        client = sales_client()
        if client is None:
            return False
        caption = service_caption(svc, title="سرویس شما آماده شد 🎉",
                                  summary=f"پرداخت سفارش #{order.id} تأیید و سرویس <b>{svc.panel_username}</b> فعال شد.")
        client.send_photo(user.telegram_id, qr_png(svc.subscription_url), caption=caption, parse_mode="HTML")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("bot service card to %s failed: %s", user.telegram_id, exc)
        return False


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
