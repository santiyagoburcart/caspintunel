"""v1.52.2 — a tiny daily Telegram summary of agency admins at or above 95 % of their limit (caspintunel addition; PAMP's
sync / enforcement untouched). Beat entry "agency: near-limit summary", 10:00 Tehran (seed). Nothing is sent when no admin is
that close. Reads the synced numbers only (no PasarGuard call); goes to OUR staff with `agency.manage` (silent ring)."""
from __future__ import annotations

THRESHOLD = 95.0
GB = 1024 ** 3


def rows(threshold: float = THRESHOLD) -> list[dict]:
    from .models import PanelAdmin

    out = []
    for a in PanelAdmin.objects.filter(has_data_limit=True, admin_limit_bytes__gt=0).order_by("username"):
        used = a.admin_used_bytes or 0
        pct = used / a.admin_limit_bytes * 100
        if pct >= threshold:
            state = "disabled" if a.status == "disabled" and not a.pamp_blocked else ("blocked" if a.pamp_blocked else "active")
            out.append({"username": a.username, "percent": round(pct, 1), "left_gb": round((a.admin_limit_bytes - used) / GB, 1),
                        "limit_gb": round(a.admin_limit_bytes / GB, 1), "state": state})
    return sorted(out, key=lambda r: (-r["percent"], r["username"]))


STATE_FA = {"blocked": "⛔️ محدود‌شده", "disabled": "⏸ غیرفعال", "active": "⚠️ فعال"}


def text(items: list[dict]) -> str:
    from apps.common.jalali import jalali_day, tehran_today

    lines = [f"📊 نماینده‌های بالای 95% سقف — {jalali_day(tehran_today())}", ""]
    for r in items:
        left = f"{max(0.0, r['left_gb']):,.1f} GB"
        lines.append(f"• {r['username']} — {r['percent']:.1f}% · باقی‌مانده {left} از {r['limit_gb']:,.0f} GB · {STATE_FA[r['state']]}")
    lines += ["", "Agency → admin → «افزایش سقف» · Near-limit agency admins (daily)"]
    return "\n".join(lines)


def send_summary() -> dict:
    from apps.common.staff_alert import alert_staff

    from .tasks import sync_enabled

    if not sync_enabled():                       # no fresh numbers without the sync
        return {"sent": 0, "admins": 0, "skipped": "sync disabled"}
    items = rows()
    if not items:
        return {"sent": 0, "admins": 0}
    sent = alert_staff(text(items), perm="agency.manage", silent=True, platform=True)
    return {"sent": sent, "admins": len(items)}
