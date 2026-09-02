"""Translate between our Plan/Service models and PasarGuard user payloads."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone as _tz

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import ExpireStrategy, ServiceStatus

# PasarGuard UserStatus values map 1:1 onto our ServiceStatus.
_PANEL_STATUS = {"active", "disabled", "limited", "expired", "on_hold"}


def _parse_dt(value) -> datetime | None:
    """Accept ISO strings, unix timestamps (int), or None."""
    if value in (None, "", 0):
        return None
    if isinstance(value, datetime):
        return value if timezone.is_aware(value) else timezone.make_aware(value, _tz.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=_tz.utc)
    dt = parse_datetime(str(value))
    if dt and timezone.is_naive(dt):
        dt = timezone.make_aware(dt, _tz.utc)
    return dt


# --- outbound: build payloads --------------------------------------
def resolve_group_ids(plan, panel) -> list[int]:
    """Plan's own group_ids win; otherwise fall back to its panel's default.
    `panel` is the plan's panel (multi-panel: service.panel == plan.panel)."""
    if plan is not None and plan.group_ids:
        return list(plan.group_ids)
    return list(panel.default_group_ids or [])


def build_create_payload(service, plan, panel) -> dict:
    # custom-volume: the cap is on the service (set from the order), not the plan
    data_limit = int(service.data_limit or 0) or int(plan.data_limit or 0)
    payload: dict = {
        "username": service.panel_username,
        "data_limit": data_limit,
        "data_limit_reset_strategy": "no_reset",
        "group_ids": resolve_group_ids(plan, panel),
        "note": f"caspintunel#{service.id}",
    }
    if plan.duration_days:
        # On-Hold: the timer starts on the user's first connection.
        payload["status"] = "on_hold"
        payload["on_hold_expire_duration"] = int(plan.duration_days) * 86400
    else:
        payload["status"] = "active"
        payload["expire"] = None  # timeless
    return payload


def build_renew_payload(service, plan) -> dict:
    """Flowchart 1.5: extend expiry + set new data_limit; usage reset separately."""
    data_limit = int(plan.data_limit or 0) or int(service.data_limit or 0)
    payload: dict = {"data_limit": data_limit, "status": "active"}
    if plan.duration_days:
        now = timezone.now()
        anchor = service.expire_at if service.expire_at and service.expire_at > now else now
        payload["expire"] = (anchor + timedelta(days=int(plan.duration_days))).isoformat()
    else:
        payload["expire"] = None
    return payload


# --- inbound: read the panel user back into our Service ----------
def _derive_strategy(api_user: dict) -> str | None:
    if api_user.get("status") == "on_hold" or api_user.get("on_hold_expire_duration"):
        return ExpireStrategy.ON_HOLD
    if api_user.get("expire"):
        return ExpireStrategy.FIXED_DATE
    return ExpireStrategy.NEVER


def _absolute_sub_url(url: str, panel) -> str:
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    base = (panel.subscription_base_url or panel.base_url).rstrip("/")
    return f"{base}/{url.lstrip('/')}"


def apply_user_to_service(service, api_user: dict, panel) -> list[str]:
    """Mutate `service` from a PasarGuard user object; return changed field names."""
    changed: list[str] = []

    def _set(field, value):
        if getattr(service, field) != value:
            setattr(service, field, value)
            changed.append(field)

    sub = _absolute_sub_url(api_user.get("subscription_url", ""), panel)
    if sub:
        _set("subscription_url", sub)

    if api_user.get("data_limit") is not None:
        _set("data_limit", int(api_user["data_limit"]))

    used = api_user.get("used_traffic")
    if used is None:
        used = api_user.get("lifetime_used_traffic")
    if used is not None:
        _set("data_used", int(used))

    _set("expire_at", _parse_dt(api_user.get("expire")))
    _set("online_at", _parse_dt(api_user.get("online_at")))

    if api_user.get("on_hold_expire_duration") is not None:
        _set("on_hold_duration", int(api_user["on_hold_expire_duration"]))
    _set("on_hold_timeout", _parse_dt(api_user.get("on_hold_timeout")))

    strategy = _derive_strategy(api_user)
    if strategy:
        _set("expire_strategy", strategy)

    status = api_user.get("status")
    if status in _PANEL_STATUS:
        _set("status", status)

    if changed:
        changed.append("updated_at")
    return changed
