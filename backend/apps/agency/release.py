"""v1.52.2 — release an enforcement block AT ONCE when a limit change leaves room (caspintunel addition).

PAMP's enforcement (`tasks.check_and_enforce_limits`, verbatim — never edited) re-enables a blocked admin only on the next sync
and only while the admin HAS a limit, so (a) a raise took up to one sync to work and (b) an admin made unlimited kept a stale
`pamp_blocked` flag forever (shown as «محدود‌شده»; incident farzin3, 2026-11-10). Every limit change made through our panel
(set / add / remove, approved requests, group-manager adds) calls `release_if_room` after PasarGuard accepted the new limit:
when the admin is `pamp_blocked` and is now unlimited or below its limit, it is enabled on PasarGuard and the flag cleared —
exactly what the next enforcement run would do. Errors never fail the limit change (the next sync still unblocks).
"""
from __future__ import annotations

import logging

from django.utils import timezone

from apps.common.models import write_audit

log = logging.getLogger("caspintunel")


def has_room(a) -> bool:
    limit = a.admin_limit_bytes if a.has_data_limit else 0
    return limit <= 0 or (a.admin_used_bytes or 0) < limit


def release_if_room(username: str, *, by: str = "", reason: str = "") -> dict | None:
    """None = nothing to do; {"released": True} or {"released": False, "error": …}."""
    from .models import PanelAdmin
    from .panel_api import PanelAPIClient

    a = PanelAdmin.objects.filter(username=username).first()
    if a is None or not a.pamp_blocked or not has_room(a):
        return None
    limit = a.admin_limit_bytes if a.has_data_limit else 0
    try:
        client = PanelAPIClient()
        client.authenticate()
        ok, msg = client.enable_admin(username)
    except Exception as exc:  # noqa: BLE001 — the limit change itself already succeeded
        ok, msg = False, str(exc)[:200]
    detail = {"admin": username, "limit_bytes": limit, "used_bytes": a.admin_used_bytes, "by": by, "reason": reason}
    if not ok:
        log.error("release_if_room(%s): enable_admin failed: %s", username, msg)
        write_audit(action="agency.enforcement_release_failed", staff=None, target=None, detail={**detail, "error": msg})
        return {"released": False, "error": msg}
    PanelAdmin.objects.filter(pk=a.pk).update(pamp_blocked=False, pamp_blocked_at=None, status="active", is_active=True,
                                              updated_at=timezone.now())
    write_audit(action="agency.enforcement_released", staff=None, target=None, detail=detail)
    return {"released": True}


def released_note(res: dict | None, lang: str = "en") -> str:
    if not res:
        return ""
    if res.get("released"):
        return " — re-enabled on the panel (the limit block is cleared)" if lang == "en" else " — ادمین دوباره فعال شد (محدودیت سقف برداشته شد)"
    return " — re-enabling failed; the next sync will retry" if lang == "en" else " — فعال‌سازی دوباره ناموفق بود؛ همگام‌سازی بعدی دوباره تلاش می‌کند"
