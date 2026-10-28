"""
High-level panel operations used by Celery tasks and (from phase 5) the order
pipeline. Every function is idempotent / retry-safe.
"""
from __future__ import annotations

import logging
import secrets
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.common.models import write_audit

from .client import PasarGuardClient
from .exceptions import PanelConflict, PanelError, PanelLinkNeedsConfirmation, PanelNameTaken, PanelNotFound
from .mappers import apply_user_to_service, build_create_payload, build_renew_payload
from .models import Panel, Service, ServiceStatus

log = logging.getLogger("caspintunel")


def get_active_panel() -> Panel | None:
    return Panel.objects.filter(is_active=True).order_by("id").first()


def client_for(panel: Panel) -> PasarGuardClient:
    return PasarGuardClient(panel)


# ------------------------------------------------------------------ account names on the panel
OWN_CREATE_SKEW = timedelta(minutes=10)


def panel_owner(api_user: dict) -> str:
    a = api_user.get("admin")
    return (a.get("username") if isinstance(a, dict) else a) or ""


def panel_account(panel: Panel, name: str) -> dict | None:
    """The panel's account with this exact name, or None. Other panel errors propagate."""
    try:
        return client_for(panel).get_user(name)
    except PanelNotFound:
        return None


def name_taken_on_panel(panel: Panel, name: str) -> dict | None:
    """For a name check before an order: the existing panel account, or None.
    Fails open when the panel can't be asked (the provisioning guard still
    refuses to attach to someone else's account)."""
    try:
        return panel_account(panel, name)
    except PanelError as exc:
        log.warning("account name check on panel %s skipped (%s)", panel.id, exc)
        return None


def created_for(api_user: dict, service: Service) -> bool:
    """True only when the panel account is the one we created for this very
    service (an earlier attempt that died before saving): our note
    `caspintunel#<id>` and not created before the service row."""
    if (api_user.get("note") or "").strip() != f"caspintunel#{service.id}":
        return False
    raw = api_user.get("created_at")
    if not raw or not service.created_at:
        return True
    try:
        from datetime import datetime, timezone as tz

        made = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        made = made if made.tzinfo else made.replace(tzinfo=tz.utc)
    except ValueError:
        return True
    return made >= service.created_at - OWN_CREATE_SKEW


def _adopt_own_or_refuse(client, service: Service) -> dict:
    """409 on create: take the account back only if it is our own earlier attempt."""
    api_user = client.get_user(service.panel_username)
    if not created_for(api_user, service):
        raise PanelNameTaken(service.panel_username, owner=panel_owner(api_user) or None)
    log.warning("panel user %s already exists from our earlier attempt — adopting", service.panel_username)
    return api_user


@transaction.atomic
def provision_service(service_id: int, plan=None) -> Service:
    """
    Create the user on the panel for `service`. Idempotent: if our own earlier
    attempt already created it (409 + our note `caspintunel#<id>`), we adopt
    it. Any other existing account with that name raises PanelNameTaken —
    we never attach a customer to someone else's account.
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
        api_user = _adopt_own_or_refuse(client, service)

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
_ENDED = (ServiceStatus.EXPIRED, ServiceStatus.LIMITED, ServiceStatus.DISABLED)
_REFRESH_THROTTLE_SECONDS = 15
_ENDED_THROTTLE_SECONDS = 60
_REFRESH_MAX_PER_CALL = 3


def refresh_watchable_services(services) -> int:
    """Sync any on_hold/pending services older than the throttle window.
    Returns how many were synced. Never raises."""
    now = timezone.now()
    synced = 0
    for svc in services:
        if synced >= _REFRESH_MAX_PER_CALL:
            break
        if svc.status in _WATCHABLE:
            wait = _REFRESH_THROTTLE_SECONDS
        elif svc.status in _ENDED:
            wait = _ENDED_THROTTLE_SECONDS            # renewed directly on the panel? show it at once
        else:
            continue
        if svc.status == ServiceStatus.PENDING and not svc.subscription_url:
            continue
        if svc.last_synced_at and (now - svc.last_synced_at).total_seconds() < wait:
            continue
        try:
            sync_service(svc.id)
            synced += 1
        except Exception as exc:  # noqa: BLE001 - a panel hiccup must not break the page
            log.info("on-view sync of service %s skipped: %s", svc.id, exc)
    return synced


# Fields that change on every read without meaning anything: PasarGuard signs the
# subscription link per request, online_at moves while the customer is connected.
_NOISE = {"subscription_url", "online_at", "updated_at"}
# What a sync result lists by name (the rest is "usage")
_KEY_FIELDS = ("status", "expire_at", "data_limit", "expire_strategy", "on_hold_duration", "device_limit")
_LIVE = (ServiceStatus.ACTIVE, ServiceStatus.ON_HOLD)


class SyncOutcome:
    """What one sync of one service did (see sync_service_detail)."""

    def __init__(self, service, changed=(), panel_change=None, error="", missing=False):
        self.service, self.changed, self.panel_change = service, list(changed), panel_change
        self.error, self.missing = error, missing

    @property
    def updated(self) -> bool:
        return bool(self.changed) or self.missing

    def row(self) -> dict:
        s = self.service
        return {"id": s.id, "panel_username": s.panel_username, "status": s.status,
                "changed": self.changed, "panel_change": self.panel_change,
                "error": self.error, "missing": self.missing}


def _panel_change(before: dict, service: Service) -> dict | None:
    """A renewal / reset / top-up / re-enable made directly on PasarGuard, or None."""
    kinds = []
    if service.expire_at and (before["expire_at"] is None or service.expire_at > before["expire_at"] + timedelta(hours=1)):
        kinds.append("expiry_extended")
    if service.data_used + 1024 ** 2 < before["data_used"]:
        kinds.append("usage_reset")
    if before["data_limit"] and (service.data_limit == 0 or service.data_limit > before["data_limit"]):
        kinds.append("volume_added")
    if before["status"] not in _LIVE and service.status in _LIVE:
        kinds.append("reactivated")
    if not kinds:
        return None
    return {"kinds": kinds, "before": {
        "status": before["status"], "data_used": before["data_used"], "data_limit": before["data_limit"],
        "expire_at": before["expire_at"].isoformat() if before["expire_at"] else None,
    }, "after": {
        "status": service.status, "data_used": service.data_used, "data_limit": service.data_limit,
        "expire_at": service.expire_at.isoformat() if service.expire_at else None,
    }}


@transaction.atomic
def sync_service_detail(service_id: int) -> SyncOutcome:
    """Pull status, expiry, volume, usage, on-hold and online from PasarGuard into our row —
    for every service, whatever its status (an expired one may have been renewed on the
    panel). A renewal / usage reset / top-up done on the panel re-arms the volume and expiry
    reminders and is written to the audit log."""
    service = Service.objects.select_for_update().select_related("panel").get(pk=service_id)
    client = client_for(service.panel)
    try:
        api_user = client.get_user(service.panel_username)
    except PanelNotFound:
        if service.status != ServiceStatus.DISABLED:
            service.status = ServiceStatus.DISABLED
            service.save(update_fields=["status", "updated_at"])
        return SyncOutcome(service, error="not_found", missing=True)

    before = {"status": service.status, "expire_at": service.expire_at,
              "data_limit": service.data_limit, "data_used": service.data_used}
    changed = apply_user_to_service(service, api_user, service.panel)
    change = _panel_change(before, service)
    if change:
        kinds = change["kinds"]
        if "usage_reset" in kinds or "volume_added" in kinds or "reactivated" in kinds:
            if service.alert_vol_sent:
                service.alert_vol_sent = False
                changed.append("alert_vol_sent")
        if "expiry_extended" in kinds or "reactivated" in kinds:
            if service.alert_exp_sent:
                service.alert_exp_sent = False
                changed.append("alert_exp_sent")
        write_audit(action="service.changed_on_panel", target=service, detail=change)
    service.last_synced_at = timezone.now()
    service.save(update_fields=sorted(set(changed) | {"last_synced_at", "updated_at"}))
    meaningful = [f for f in dict.fromkeys(changed) if f not in _NOISE and not f.startswith("alert_")]
    return SyncOutcome(service, meaningful, change)


def sync_service(service_id: int) -> Service:
    return sync_service_detail(service_id).service


def syncable_services():
    """Every service that has an account on a panel (pending ones not created yet are skipped)."""
    return (Service.objects.exclude(panel_username="")
            .exclude(status=ServiceStatus.PENDING, subscription_url="")
            .filter(panel__is_active=True))


def sync_services(ids, *, budget_seconds: float | None = None) -> dict:
    """Sync these services one by one and say what happened:
    {checked, updated, errors, skipped, rows (only the changed / failed ones)}.
    With a time budget, whatever is left when it runs out is reported as `skipped`."""
    import time

    start = time.monotonic()
    out = {"checked": 0, "updated": 0, "errors": 0, "skipped": 0, "rows": []}
    ids = list(ids)
    for i, sid in enumerate(ids):
        if budget_seconds is not None and time.monotonic() - start > budget_seconds:
            out["skipped"] = len(ids) - i
            out["skipped_ids"] = ids[i:]
            break
        try:
            res = sync_service_detail(sid)
        except Service.DoesNotExist:
            continue
        except PanelError as exc:
            out["checked"] += 1
            out["errors"] += 1
            svc = Service.objects.filter(pk=sid).only("id", "panel_username", "status").first()
            out["rows"].append({"id": sid, "panel_username": svc.panel_username if svc else "", "status": svc.status if svc else "",
                                "changed": [], "panel_change": None, "error": str(exc)[:200], "missing": False})
            continue
        out["checked"] += 1
        if res.missing:
            out["errors"] += 1
            out["rows"].append(res.row())
        elif res.updated:
            out["updated"] += 1
            out["rows"].append(res.row())
    out["at"] = timezone.now().isoformat()
    return out


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
    existing = panel_account(panel, name)        # never adopt silently: "Link existing account" is the explicit way
    if existing is not None:
        raise PanelNameTaken(existing.get("username") or name, owner=panel_owner(existing) or None)

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
        api_user = _adopt_own_or_refuse(client, service)

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
                   on_hold_days=None, group_ids=None, note=None, hwid_limit=None, staff=None) -> tuple[Service, dict]:
    """Admin "full edit": write the changes to PasarGuard first, then read the
    account back and mirror it onto our row (so our DB only ever reflects what
    the panel accepted). Only the arguments that are passed are sent.

    - status: active / on_hold / disabled
    - data_limit: bytes, 0 = unlimited
    - expire_at: aware datetime, or None = no expiry (ignored for on_hold)
    - on_hold_days: on_hold only — the timer that starts on first connection
    - group_ids: list of panel group ids
    - note: the panel-side note
    - hwid_limit: device (HWID) limit, 0 = unlimited

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
    if hwid_limit is not None:
        payload["hwid_limit"] = max(0, int(hwid_limit))

    before = {"status": service.status, "data_limit": service.data_limit, "device_limit": service.device_limit,
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


def search_panel_users(panel: Panel, search: str = "", *, limit: int = 20) -> list[dict]:
    """Live search of a panel's accounts (by username) for the admin "link an
    existing panel account" flow. Each row says whether it is already linked
    to one of our users."""
    users, _total = client_for(panel).list_users(search=search.strip(), limit=limit)
    names = [u["username"] for u in users if u.get("username")]
    match = Q(pk__in=[])
    for n in names:
        match |= Q(panel_username__iexact=n)
    linked = {s.panel_username.lower(): s
              for s in Service.objects.filter(match, panel=panel).select_related("user")}
    out = []
    for u in users:
        name = u.get("username") or ""
        svc = linked.get(name.lower())
        out.append({
            "username": name,
            "owner": panel_owner(u),
            "other_admin": bool(panel_owner(u)) and panel_owner(u) != panel.admin_username,
            "status": u.get("status"),
            "used_traffic": int(u.get("used_traffic") or 0),
            "data_limit": int(u.get("data_limit") or 0),
            "expire": u.get("expire"),
            "online_at": u.get("online_at"),
            "on_hold_expire_duration": u.get("on_hold_expire_duration"),
            "linked": ({"service_id": svc.id, "user_id": svc.user_id, "username": svc.user.username,
                        "user_deleted": svc.user.deleted_at is not None} if svc else None),
        })
    return out


@transaction.atomic
def link_existing_service(*, user, panel: Panel, panel_username: str, plan=None, staff=None,
                          confirm_other_admin: bool = False) -> Service:
    """Adopt an account that already exists on the panel: create our Service
    (mirrored from the live panel data) + a completed `imported` Order with no
    payment. Nothing is changed on the panel."""
    from apps.orders.models import Order, OrderStatus, OrderType

    name = (panel_username or "").strip()
    if not name:
        raise ValueError("panel_username is required")
    if plan is not None and plan.panel_id != panel.id:
        raise ValueError(f"plan {plan.id} belongs to panel {plan.panel_id}, not panel {panel.id}")
    existing = Service.objects.filter(panel=panel, panel_username__iexact=name).select_related("user").first()
    if existing is not None:
        raise ServiceAlreadyLinked(existing)

    api_user = client_for(panel).get_user(name)          # PanelNotFound -> caller
    name = api_user.get("username") or name               # the panel's exact spelling
    owner = panel_owner(api_user)
    if owner and owner != panel.admin_username and not confirm_other_admin:
        raise PanelLinkNeedsConfirmation(name, owner=owner)   # e.g. a reseller's customer: staff must choose explicitly

    service = Service(user=user, panel=panel, panel_username=name, current_plan=plan, source="import")
    apply_user_to_service(service, api_user, panel)
    service.last_synced_at = timezone.now()
    service.save()

    order = Order(
        user=user, plan=plan, service=service, type=OrderType.IMPORTED,
        requested_account_name=name, amount=0, amount_unique=0,
        unique_expire_at=timezone.now(), status=OrderStatus.COMPLETED, source="admin",
    )
    order.sync_unique_lock()
    order.save()

    write_audit(action="service.linked_existing", staff=staff, target=service, detail={
        "panel": panel.id, "panel_username": name, "user": user.id, "panel_owner": owner,
        "other_admin_confirmed": bool(confirm_other_admin and owner and owner != panel.admin_username),
        "plan": plan.id if plan else None, "order": order.id,
    })
    return service


class ServiceAlreadyLinked(Exception):
    def __init__(self, service: Service):
        self.service = service
        super().__init__(
            f"panel account {service.panel_username} is already linked to user "
            f"{service.user.username} (service #{service.id})"
        )


def disable_service_on_panel(service: Service) -> str:
    """Disable one service on its panel and mirror the result (used when a user
    is deleted). Returns "disabled" or "missing" (already gone from the panel);
    raises PanelError on any other failure. Never deletes anything."""
    client = client_for(service.panel)
    try:
        client.update_user(service.panel_username, {"status": ServiceStatus.DISABLED})
        api_user = client.get_user(service.panel_username)
    except PanelNotFound:
        result = "missing"
    else:
        apply_user_to_service(service, api_user, service.panel)
        result = "disabled"
    service.status = ServiceStatus.DISABLED
    service.last_synced_at = timezone.now()
    service.save()
    return result
