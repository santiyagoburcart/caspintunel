"""JSON shapes for the admin API. Every number is computed by the ported PAMP
code (models properties, enrich._enrich / portal_state / dashboard_numbers);
this module only selects and names them — no arithmetic here."""
from __future__ import annotations

from .enrich import _enrich, dashboard_numbers, portal_state
from .models import AdminGroup, PanelAdmin, SyncLog, UserTrafficSnapshot


def groups_of(username: str, groups=None) -> list[dict]:
    groups = groups if groups is not None else list(AdminGroup.objects.all())
    return [{"id": g.id, "owner": g.owner_username} for g in groups if username in g.get_all_usernames()]


def admin_row(a: PanelAdmin, groups=None) -> dict:
    e = _enrich(a)
    return {
        "username": a.username,
        "status": a.status,
        "status_code": a.status_code,            # active | panel_disabled | pamp_limited
        "is_sudo": a.is_sudo,
        "is_unlimited": a.is_unlimited,
        "has_data_limit": a.has_data_limit,
        "pamp_blocked": a.pamp_blocked,
        "usage_percent": a.usage_percent,
        "user_count": a.user_count,
        "active_user_count": a.active_user_count,
        "user_counts": {"active": a.active_user_count, "on_hold": a.on_hold_users, "limited": a.limited_users,
                        "disabled": a.disabled_users, "expired": a.expired_users},
        "admin_limit_fmt": a.admin_limit_fmt,
        "total_sold_fmt": a.total_user_limit_fmt,           # PAMP "Total Sold"
        "sold_limit_fmt": e["sold_limit_fmt"],
        "sold_limit_value": e["sold_limit_value"],
        "hidden_fmt": e["hidden_traffic_fmt"],              # as PAMP's portal/detail shows it
        "remaining_fmt": a.admin_remaining_fmt,
        "used_fmt": a.admin_used_fmt,
        "last_synced_at": a.last_synced_at,
        "groups": groups_of(a.username, groups),
    }


def admin_detail(a: PanelAdmin) -> dict:
    e = _enrich(a)
    p = portal_state(a)
    try:
        lim = a.limit_config
        limit_config = {"limit_bytes": lim.limit_bytes, "warning_sent_80": lim.warning_sent_80,
                        "telegram_username": lim.telegram_username, "support_telegram": lim.support_telegram}
    except Exception:  # noqa: BLE001 — PAMP treats a missing AdminLimit the same way
        limit_config = None
    snaps = UserTrafficSnapshot.objects.filter(panel_admin=a).order_by("-used_traffic_bytes", "user_username")
    from .models import _fmt_bytes

    return {
        **admin_row(a),
        "is_active": a.is_active,
        "admin_limit_bytes": a.admin_limit_bytes,
        "admin_limit_gb": a.admin_limit_gb,
        "total_user_used_fmt": a.total_user_used_fmt,
        "hidden_traffic_clamped_fmt": a.hidden_traffic_fmt,  # model property (max 0)
        "deleted_used_fmt": e["deleted_used_fmt"],
        "deleted_used_bytes": e["deleted_used_bytes"],
        "deleted_traffic_reset_at": a.deleted_traffic_reset_at,
        "counts": {"active": a.active_user_count, "on_hold": a.on_hold_users, "limited": a.limited_users,
                   "disabled": a.disabled_users, "expired": a.expired_users, "total": a.user_count},
        "portal": p,
        "pamp_blocked_at": a.pamp_blocked_at,
        "limit_config": limit_config,
        "snapshots": {
            "count": snaps.count(),
            "rows": [{"user": s.user_username, "used_fmt": _fmt_bytes(s.used_traffic_bytes), "last_seen": s.last_seen}
                     for s in snaps[:300]],
        },
        "recent_syncs": [sync_row(s) for s in SyncLog.objects.order_by("-id")[:15]],
    }


def sync_row(s: SyncLog) -> dict:
    return {"id": s.id, "status": s.status, "admins_synced": s.admins_synced, "error_message": s.error_message,
            "duration_seconds": s.duration_seconds, "created_at": s.created_at}


def dashboard() -> dict:
    d = dashboard_numbers()
    last = SyncLog.objects.order_by("-id").first()
    return {
        "admin_count": d["admin_count"], "active_count": d["active_count"], "disabled_count": d["disabled_count"],
        "pamp_limited_count": d["pamp_limited_count"], "near_limit_count": d["near_limit_count"],
        "total_sold_fmt": d["total_limit_fmt"], "total_used_fmt": d["total_used_fmt"],
        "total_remaining_fmt": d["total_remaining_fmt"], "total_hidden_fmt": d["total_hidden_fmt"],
        "total_users": d["total_users"], "total_active": d["total_active"],
        "over_limit": [{**o, "status_code": PanelAdmin.objects.get(username=o["username"]).status_code}
                       for o in d["over_limit_admins"]],
        "last_sync": sync_row(last) if last else None,
    }


def portal_link() -> dict:
    """The reseller-portal address — follows the configured portal path (docs/paths.md)."""
    from apps.settings_app import paths
    from apps.settings_app.models import SiteConfig

    domain = (SiteConfig.load().site_domain or "").strip().strip("/")
    path = paths.state()["portal"]
    return {"path": path, "url": f"https://{domain}{path}/" if domain else f"{path}/"}
