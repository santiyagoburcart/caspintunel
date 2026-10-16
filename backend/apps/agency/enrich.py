"""Numbers PAMP computes in its VIEWS (not in the models) — ported 1:1 from
PAMP v1.5.3 `admins/views.py` (sha256 cf8e262f…65cf):

  _fmt_bytes_signed, _enrich           → verbatim (portal / admin-detail numbers;
                                         note: hidden traffic is NOT clamped here)
  dashboard_numbers()                  → body of dashboard_v2 (totals, over-limit list)
                                         + total_hidden from the v1 `dashboard` view
  portal_state(panel_admin)            → body of portal_v2 (block state, 80% warning)

Only the surrounding function signatures/returns are new.
"""
from django.db.models import Sum

from .models import PanelAdmin, _fmt_bytes


def _fmt_bytes_signed(b: int) -> str:
    """Format a byte count with an explicit +/- sign. Zero returns '0 GB'."""
    if b == 0:
        return "0 GB"
    sign = "+" if b > 0 else "-"
    val = abs(b)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if val < 1024:
            return f"{sign}{val:.2f} {unit}"
        val /= 1024
    return f"{sign}{val:.2f} PB"


def hidden_value(a) -> int:
    """The unclamped hidden traffic exactly as _enrich computes it (for sorting only)."""
    return a.total_user_limit - a.total_user_used - a.admin_remaining


def _enrich(panel_admin):
    """Return context dict with all formatted values for portal/detail views."""
    a = panel_admin
    hidden = a.total_user_limit - a.total_user_used - a.admin_remaining
    if a.is_unlimited:
        sold_fmt = "0 GB"
        sold_val = 0
    else:
        sold_val = a.sold_limit_bytes
        sold_fmt = _fmt_bytes_signed(sold_val)
    return {
        'obj': a,
        'panel_admin': a,
        'hidden_traffic_fmt': _fmt_bytes(hidden),
        'total_user_limit_fmt': a.total_user_limit_fmt,
        'total_user_used_fmt': a.total_user_used_fmt,
        'admin_limit_fmt': a.admin_limit_fmt,
        'admin_used_fmt': a.admin_used_fmt,
        'admin_remaining_fmt': a.admin_remaining_fmt,
        'usage_percent': a.usage_percent,
        'sold_limit_fmt': sold_fmt,
        'sold_limit_value': sold_val,
        'deleted_used_fmt': _fmt_bytes(a.deleted_users_used_bytes or 0),
        'deleted_used_bytes': a.deleted_users_used_bytes or 0,
    }



def dashboard_numbers():
    """PAMP dashboard_v2 numbers (same code; returns what it put in the context)."""
    admins = PanelAdmin.objects.all()
    totals = admins.aggregate(
        total_limit=Sum('total_user_limit'),
        total_used=Sum('total_user_used'),
        total_remaining=Sum('admin_remaining'),
        total_users=Sum('user_count'),
        total_active=Sum('active_user_count'),
    )

    total_limit = totals['total_limit'] or 0
    total_used = totals['total_used'] or 0
    total_remaining = totals['total_remaining'] or 0

    over_limit_list = []
    for a in PanelAdmin.objects.all():
        if not a.admin_limit_bytes or a.admin_limit_bytes <= 0:
            continue
        pct = round((a.admin_used_bytes / a.admin_limit_bytes) * 100, 1)
        if pct < 80:
            continue
        over_limit_list.append({
            'username': a.username,
            'limit_fmt': _fmt_bytes(a.admin_limit_bytes),
            'used_fmt': _fmt_bytes(a.admin_used_bytes),
            'pct': pct,
            'state': 'over' if pct >= 100 else 'at_risk',
            'status_label': a.status_label,
            'status_color': a.status_color,
        })
    over_limit_list.sort(key=lambda x: x['pct'], reverse=True)

    return {
        'admin_count': admins.count(),
        'active_count': PanelAdmin.objects.filter(status='active').count(),
        'disabled_count': PanelAdmin.objects.filter(status='disabled').count(),
        'pamp_limited_count': PanelAdmin.objects.filter(pamp_blocked=True).count(),
        'near_limit_count': len(over_limit_list),
        'total_limit_fmt': _fmt_bytes(total_limit),
        'total_used_fmt': _fmt_bytes(total_used),
        'total_remaining_fmt': _fmt_bytes(total_remaining),
        'total_users': totals['total_users'] or 0,
        'total_active': totals['total_active'] or 0,
        'over_limit_admins': over_limit_list,
        'total_limit': total_limit, 'total_used': total_used, 'total_remaining': total_remaining,
        # PAMP's v1 `dashboard` view: total_hidden = total_limit - total_used - total_remaining (verbatim)
        'total_hidden': total_limit - total_used - total_remaining,
        'total_hidden_fmt': _fmt_bytes(total_limit - total_used - total_remaining),
    }


def portal_state(panel_admin):
    """PAMP portal_v2 block / warning state for one admin (same code)."""
    is_blocked = panel_admin.status == 'disabled' or panel_admin.pamp_blocked
    block_reason = 'disabled' if panel_admin.status == 'disabled' else ('pamp_limited' if panel_admin.pamp_blocked else None)
    try:
        support_telegram = panel_admin.limit_config.support_telegram or '@support'
    except Exception:
        support_telegram = '@support'

    show_warning = False
    warning_pct = 0
    if panel_admin.has_data_limit and panel_admin.admin_limit_bytes > 0:
        warning_pct = round((panel_admin.admin_used_bytes / panel_admin.admin_limit_bytes) * 100, 1)
        show_warning = warning_pct >= 80

    return {
        'is_blocked': is_blocked,
        'block_reason': block_reason,
        'support_telegram': support_telegram,
        'show_warning': show_warning,
        'warning_pct': warning_pct,
    }
