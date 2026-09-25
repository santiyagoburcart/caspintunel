"""
High-level panel operations used by Celery tasks and (from phase 5) the order
pipeline. Every function is idempotent / retry-safe.
"""
from __future__ import annotations

import logging
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.common.models import write_audit

from .client import PasarGuardClient
from .exceptions import PanelConflict, PanelError, PanelNotFound
from .mappers import apply_user_to_service, build_create_payload, build_renew_payload
from .models import Panel, Service, ServiceStatus

log = logging.getLogger("caspintunel")


def get_active_panel() -> Panel | None:
    return Panel.objects.filter(is_active=True).order_by("id").first()


def client_for(panel: Panel) -> PasarGuardClient:
    return PasarGuardClient(panel)


@transaction.atomic
def provision_service(service_id: int, plan=None) -> Service:
    """
    Create the user on the panel for `service`. Idempotent: if the username
    already exists on the panel (409 or our record already provisioned), we
    adopt it instead of failing.
    """
    service = Service.objects.select_for_update().select_related("panel", "current_plan").get(pk=service_id)
    plan = plan or service.current_plan
    if plan is None:
        raise ValueError(f"service {service_id} has no plan to provision")

    client = client_for(service.panel)

    if service.subscription_url and service.status not in (ServiceStatus.PENDING,):
        # already provisioned — just resync
        return sync_service(service_id)

    try:
        api_user = client.create_user(build_create_payload(service, plan, service.panel))
    except PanelConflict:
        log.warning("panel user %s already exists — adopting", service.panel_username)
        api_user = client.get_user(service.panel_username)

    service.current_plan = plan
    apply_user_to_service(service, api_user, service.panel)
    if service.status == ServiceStatus.PENDING:
        service.status = ServiceStatus.ON_HOLD if plan.duration_days else ServiceStatus.ACTIVE
    service.save()
    write_audit(action="service.provisioned", target=service, detail={"plan": plan.id})
    return service


@transaction.atomic
def renew_service(service_id: int, plan) -> Service:
    """Flowchart 1.5: PUT the same username, reset usage, keep subscription_url."""
    service = Service.objects.select_for_update().select_related("panel").get(pk=service_id)
    if plan is not None and getattr(plan, "panel_id", service.panel_id) != service.panel_id:
        raise PanelError(
            f"plan {plan.id} is on panel {plan.panel_id}, service {service_id} is on {service.panel_id}"
        )
    client = client_for(service.panel)

    api_user = client.update_user(service.panel_username, build_renew_payload(service, plan))
    try:
        client.reset_user_usage(service.panel_username)
    except PanelNotFound:
        pass
    api_user = client.get_user(service.panel_username)

    service.current_plan = plan
    service.alert_vol_sent = False
    service.alert_exp_sent = False
    apply_user_to_service(service, api_user, service.panel)
    service.status = ServiceStatus.ACTIVE
    service.save()
    write_audit(action="service.renewed", target=service, detail={"plan": plan.id})
    return service


@transaction.atomic
def add_service_data_limit(service_id: int, extra_bytes: int) -> Service:
    """Add-on volume: bump the panel user's data_limit (0 = unlimited, left as-is)."""
    service = Service.objects.select_for_update().select_related("panel").get(pk=service_id)
    client = client_for(service.panel)
    current = client.get_user(service.panel_username)
    base = int(current.get("data_limit") or 0)
    if base == 0:
        return service  # unlimited already
    client.update_user(service.panel_username, {"data_limit": base + int(extra_bytes)})
    api_user = client.get_user(service.panel_username)
    apply_user_to_service(service, api_user, service.panel)
    service.save()
    write_audit(action="service.volume_added", target=service, detail={"extra_bytes": int(extra_bytes)})
    return service


def reset_service_usage(service_id: int, *, staff=None) -> Service:
    service = Service.objects.select_related("panel").get(pk=service_id)
    client = client_for(service.panel)
    client.reset_user_usage(service.panel_username)
    Service.objects.filter(pk=service_id).update(alert_vol_sent=False)
    if staff is not None:
        write_audit(action="service.usage_reset", staff=staff, target=service, detail={})
    return sync_service(service_id)


# on_hold / pending services flip the instant the customer first connects, so we
# re-pull them from the panel whenever the customer looks at their services (site
# poll or bot). Throttled per service + capped per call so an open dashboard
# never hammers the panel.
_WATCHABLE = (ServiceStatus.ON_HOLD, ServiceStatus.PENDING)
_REFRESH_THROTTLE_SECONDS = 15
_REFRESH_MAX_PER_CALL = 3


def refresh_watchable_services(services) -> int:
    """Sync any on_hold/pending services older than the throttle window.
    Returns how many were synced. Never raises."""
    now = timezone.now()
    synced = 0
    for svc in services:
        if synced >= _REFRESH_MAX_PER_CALL:
            break
        if svc.status not in _WATCHABLE:
            continue
        if svc.last_synced_at and (now - svc.last_synced_at).total_seconds() < _REFRESH_THROTTLE_SECONDS:
            continue
        try:
            sync_service(svc.id)
            synced += 1
        except Exception as exc:  # noqa: BLE001 - a panel hiccup must not break the page
            log.info("on-view sync of service %s skipped: %s", svc.id, exc)
    return synced


@transaction.atomic
def sync_service(service_id: int) -> Service:
    service = Service.objects.select_for_update().select_related("panel").get(pk=service_id)
    client = client_for(service.panel)
    try:
        api_user = client.get_user(service.panel_username)
    except PanelNotFound:
        if service.status != ServiceStatus.DISABLED:
            service.status = ServiceStatus.DISABLED
            service.save(update_fields=["status", "updated_at"])
        return service

    changed = apply_user_to_service(service, api_user, service.panel)
    service.last_synced_at = timezone.now()
    service.save(update_fields=sorted(set(changed) | {"last_synced_at", "updated_at"}))
    return service


@transaction.atomic
def apply_scheduled_renewal(scheduled_renewal_id: int) -> Service:
    """Applies a previously-paid renewal once the service actually reached the
    end of its cycle (see apps.panel.tasks.apply_due_scheduled_renewals) —
    mode A (reset) just delegates to the existing renew_service; mode B
    (carry_over) folds in whatever time/volume was left first."""
    from apps.orders.models import ScheduledRenewal
    from apps.plans.models import RenewalMode

    renewal = (
        ScheduledRenewal.objects.select_for_update()
        .select_related("service", "service__panel", "service__user", "plan")
        .get(pk=scheduled_renewal_id)
    )
    if renewal.applied_at is not None:
        return renewal.service  # already applied — never double-apply

    service = renewal.service
    if renewal.renewal_mode == RenewalMode.CARRY_OVER:
        _apply_carry_over_renewal(service, renewal.plan, renewal.carry_over_data)
    else:
        renew_service(service.id, renewal.plan)

    renewal.applied_at = timezone.now()
    renewal.save(update_fields=["applied_at", "updated_at"])

    try:
        from apps.notifications.dispatch import notify_user

        notify_user(
            service.user,
            title="سرویس شما تمدید شد 🎉",
            body=f"سرویس {service.panel_username} با موفقیت تمدید شد و اکنون فعال است.",
            via_site=True, via_bot=True, via_email=True,
        )
    except Exception as exc:  # noqa: BLE001 - notification must not fail the renewal
        log.warning("renewal notification for service %s failed: %s", service.id, exc)

    return service


def _apply_carry_over_renewal(service: Service, plan, carry_over_data: str) -> Service:
    """Mode B: fold whatever time/volume the service had left into the new
    plan's amounts, instead of discarding it. Which dimension gets carried is
    whichever the customer actually still had when the cycle ended — a
    time-expired service may still have unused volume (carry that), while a
    volume-exhausted one may still have time left (carry that instead)."""
    now = timezone.now()
    extra_bytes = 0
    if carry_over_data in ("both", "volume_only") and service.data_limit:
        extra_bytes = max(0, service.data_limit - service.data_used)
    extra_seconds = 0
    if carry_over_data in ("both", "time_only") and service.expire_at and service.expire_at > now:
        extra_seconds = int((service.expire_at - now).total_seconds())

    new_data_limit = int(plan.data_limit or 0)
    if new_data_limit and extra_bytes:
        new_data_limit += extra_bytes
    # if the plan itself is unlimited (0), it stays unlimited regardless

    payload = {"data_limit": new_data_limit, "status": "active"}
    if plan.duration_days:
        total_seconds = int(plan.duration_days) * 86400 + extra_seconds
        payload["expire"] = (now + timedelta(seconds=total_seconds)).isoformat()
    else:
        payload["expire"] = None

    client = client_for(service.panel)
    client.update_user(service.panel_username, payload)
    try:
        client.reset_user_usage(service.panel_username)
    except PanelNotFound:
        pass
    api_user = client.get_user(service.panel_username)

    service.current_plan = plan
    service.alert_vol_sent = False
    service.alert_exp_sent = False
    apply_user_to_service(service, api_user, service.panel)
    service.status = ServiceStatus.ACTIVE
    service.save()
    write_audit(
        action="service.renewed_carry_over", target=service,
        detail={"plan": plan.id, "carry_over_data": carry_over_data,
                "extra_bytes": extra_bytes, "extra_seconds": extra_seconds},
    )
    return service


@transaction.atomic
def set_service_status(service_id: int, status: str, *, staff=None) -> Service:
    """Admin action: flip a service between active / on_hold / disabled on
    the panel, then mirror the result back onto our row."""
    if status not in (ServiceStatus.ACTIVE, ServiceStatus.ON_HOLD, ServiceStatus.DISABLED):
        raise ValueError(f"unsupported status: {status}")
    service = Service.objects.select_for_update().select_related("panel").get(pk=service_id)
    client = client_for(service.panel)
    client.update_user(service.panel_username, {"status": status})
    api_user = client.get_user(service.panel_username)
    changed = apply_user_to_service(service, api_user, service.panel)
    service.last_synced_at = timezone.now()
    service.save(update_fields=sorted(set(changed) | {"last_synced_at", "updated_at"}))
    write_audit(action="service.status_changed", staff=staff, target=service, detail={"status": status})
    return service


def _auto_account_name(panel: Panel) -> str:
    for _ in range(20):
        candidate = f"m_{secrets.token_hex(4)}"
        if not Service.objects.filter(panel=panel, panel_username=candidate).exists():
            return candidate
    raise PanelError("could not allocate a unique account name, please retry")


@transaction.atomic
def create_manual_service(*, user, plan, panel: Panel | None = None, group_ids=None,
                          account_name: str | None = None, staff=None) -> Service:
    """Admin manual creation (فاز ۲): no payment — a completed `Order`
    (type=manual) is recorded for the audit trail, then the real panel
    account + our Service row."""
    from apps.orders.models import Order, OrderStatus, OrderType

    panel = panel or plan.panel
    if plan.panel_id != panel.id:
        raise PanelError(f"plan {plan.id} belongs to panel {plan.panel_id}, not panel {panel.id}")

    name = (account_name or "").strip() or _auto_account_name(panel)
    if Service.objects.filter(panel=panel, panel_username__iexact=name).exists():
        raise PanelError("that account name is already taken on this panel")

    order = Order(
        user=user, plan=plan, type=OrderType.MANUAL,
        requested_account_name=name, amount=0, amount_unique=0,
        unique_expire_at=timezone.now(), status=OrderStatus.COMPLETED, source="admin",
    )
    order.sync_unique_lock()
    order.save()

    service = Service.objects.create(
        user=user, panel=panel, panel_username=name, current_plan=plan, source="admin",
    )
    order.service = service
    order.save(update_fields=["service", "updated_at"])

    client = client_for(panel)
    payload = build_create_payload(service, plan, panel)
    if group_ids:
        payload["group_ids"] = list(group_ids)
    try:
        api_user = client.create_user(payload)
    except PanelConflict:
        log.warning("manual create: panel user %s already exists — adopting", name)
        api_user = client.get_user(name)

    apply_user_to_service(service, api_user, panel)
    if service.status == ServiceStatus.PENDING:
        service.status = ServiceStatus.ON_HOLD if plan.duration_days else ServiceStatus.ACTIVE
    service.last_synced_at = timezone.now()
    service.save()

    write_audit(action="service.created_manually", staff=staff, target=service,
                detail={"plan": plan.id, "order": order.id})
    return service


@transaction.atomic
def delete_service(service_id: int, *, staff=None) -> None:
    """Admin action: permanently remove a service — deletes the panel account
    (best-effort; already-gone on the panel is not an error) then our row.
    Orders that reference it keep their audit trail (service FK is SET_NULL)."""
    service = Service.objects.select_for_update().select_related("panel").get(pk=service_id)
    client = client_for(service.panel)
    try:
        client.delete_user(service.panel_username)
    except PanelNotFound:
        pass
    write_audit(action="service.deleted", staff=staff, target=service,
                detail={"panel_username": service.panel_username, "panel": service.panel_id})
    service.delete()


@transaction.atomic
def revoke_subscription(service_id: int, *, staff=None) -> Service:
    """Issues a new subscription link for the service's panel account,
    invalidating the old one — every device on the previous link is
    disconnected until it's reconfigured with the new one."""
    service = Service.objects.select_for_update().select_related("panel").get(pk=service_id)
    client = client_for(service.panel)
    client.revoke_subscription(service.panel_username)
    api_user = client.get_user(service.panel_username)
    changed = apply_user_to_service(service, api_user, service.panel)
    service.last_synced_at = timezone.now()
    service.save(update_fields=sorted(set(changed) | {"last_synced_at", "updated_at"}))
    write_audit(action="service.subscription_revoked", staff=staff, target=service, detail={})
    return service


_UNSET = object()
_EDITABLE_STATUSES = (ServiceStatus.ACTIVE, ServiceStatus.ON_HOLD, ServiceStatus.DISABLED)


@transaction.atomic
def update_service(service_id: int, *, status=None, data_limit=None, expire_at=_UNSET,
                   on_hold_days=None, group_ids=None, note=None, staff=None) -> tuple[Service, dict]:
    """Admin "full edit": write the changes to PasarGuard first, then read the
    account back and mirror it onto our row (so our DB only ever reflects what
    the panel accepted). Only the arguments that are passed are sent.

    - status: active / on_hold / disabled
    - data_limit: bytes, 0 = unlimited
    - expire_at: aware datetime, or None = no expiry (ignored for on_hold)
    - on_hold_days: on_hold only — the timer that starts on first connection
    - group_ids: list of panel group ids
    - note: the panel-side note

    Returns (service, live panel user)."""
    service = Service.objects.select_for_update().select_related("panel").get(pk=service_id)
    payload: dict = {}
    if status is not None:
        if status not in _EDITABLE_STATUSES:
            raise ValueError(f"unsupported status: {status}")
        payload["status"] = status
    if data_limit is not None:
        payload["data_limit"] = max(0, int(data_limit))
    target_status = status or service.status
    if target_status == ServiceStatus.ON_HOLD:
        days = on_hold_days or (service.on_hold_duration // 86400 if service.on_hold_duration else None)
        if status == ServiceStatus.ON_HOLD or on_hold_days is not None:
            if not days:
                raise ValueError("on_hold needs a duration (on_hold_days)")
            payload["on_hold_expire_duration"] = int(days) * 86400
            payload["expire"] = None
    elif expire_at is not _UNSET:
        payload["expire"] = expire_at.isoformat() if expire_at else None
    if group_ids is not None:
        payload["group_ids"] = [int(g) for g in group_ids]
    if note is not None:
        payload["note"] = note

    before = {"status": service.status, "data_limit": service.data_limit,
              "expire_at": service.expire_at.isoformat() if service.expire_at else None}
    client = client_for(service.panel)
    if payload:
        client.update_user(service.panel_username, payload)       # panel first…
    api_user = client.get_user(service.panel_username)            # …then mirror what it accepted
    changed = apply_user_to_service(service, api_user, service.panel)
    if "data_limit" in payload:
        service.alert_vol_sent = False
        changed.append("alert_vol_sent")
    if "expire" in payload or "on_hold_expire_duration" in payload:
        service.alert_exp_sent = False
        changed.append("alert_exp_sent")
    service.last_synced_at = timezone.now()
    service.save(update_fields=sorted(set(changed) | {"last_synced_at", "updated_at"}))
    write_audit(action="service.edited", staff=staff, target=service, detail={
        "sent": {k: v for k, v in payload.items() if k != "note"} | ({"note": "…"} if "note" in payload else {}),
        "before": before,
    })
    return service, api_user
