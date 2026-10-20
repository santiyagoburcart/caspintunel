"""Write actions of the agency panel — the logic of PAMP v1.5.3 `admins/views.py`
(set_limit, remove_limit, admin_action, reset_deleted_traffic, trigger_sync,
save/delete_account_group) ported verbatim, minus the HTTP/HTML wrapping:
each returns (ok, message).

GATE: until the cut-over from the Finland PAMP every action is refused —
Finland is still the live instance, and a write here would either touch the
shared panel twice or be overwritten by the cut-over import. The gate opens
when `agency_sync_enabled` is turned on (= the cut-over).
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import AdminGroup, PanelAdmin
from .tasks import sync_enabled

PRE_CUTOVER = "available after the final cut-over from the Finland PAMP"


class PreCutover(Exception):
    pass


def writes_enabled() -> bool:
    return sync_enabled()


def _gate():
    if not writes_enabled():
        raise PreCutover(PRE_CUTOVER)


def new_limit_for(current_limit: int, action: str, value_gb: float):
    """PAMP set_limit's arithmetic, verbatim (None = unknown action)."""
    gb = 1024 ** 3
    if action == 'set':
        return int(value_gb * gb)
    elif action == 'add':
        return int(current_limit + value_gb * gb)
    elif action == 'reduce':
        return max(0, int(current_limit - value_gb * gb))
    return None


def preview_set_limit(username: str, action: str, value_gb) -> dict:
    """What set_limit WOULD do — no panel call, nothing saved. For the confirm dialog."""
    from .ledger import quote_quota_charge
    from .models import _fmt_bytes

    try:
        value_gb = float(value_gb or 0)
    except (TypeError, ValueError):
        raise ValueError("Invalid value")
    if value_gb < 0:
        raise ValueError("Invalid value")
    a = get_object_or_404(PanelAdmin, username=username)
    old = a.admin_limit_bytes or 0
    new = new_limit_for(old, action, value_gb)
    if new is None:
        raise ValueError("Unknown action")
    fmt = lambda b: "Unlimited" if b <= 0 else _fmt_bytes(b)
    q = quote_quota_charge(username, old, new)
    return {"old_limit_fmt": fmt(old), "new_limit_fmt": fmt(new), "old_limit_bytes": old, "new_limit_bytes": new,
            "remaining_after_fmt": fmt(max(0, new - a.admin_used_bytes)) if new > 0 else "Unlimited",
            "charge": q}


def set_limit(username: str, action: str, value_gb, by: str = "") -> tuple[bool, str]:
    """PAMP set_limit: action set | add | reduce, value in GB (1024**3).
    caspintunel addition after PAMP's logic: an increase records a quota charge
    in the ledger (ledger.record_quota_charge) — PAMP's numbers are untouched."""
    _gate()
    try:
        value_gb = float(value_gb or 0)
    except (TypeError, ValueError):
        return False, "Invalid value"

    from .panel_api import PanelAPIClient

    panel_admin = get_object_or_404(PanelAdmin, username=username)
    client = PanelAPIClient()
    client.authenticate()

    current_limit = panel_admin.admin_limit_bytes or 0
    gb = 1024 ** 3

    new_limit_bytes = new_limit_for(current_limit, action, value_gb)
    if new_limit_bytes is None:
        return False, "Unknown action"

    success, message = client.set_admin_data_limit(username, new_limit_bytes)
    if not success:
        return False, f"Failed: {message}"

    panel_admin.admin_limit_bytes = new_limit_bytes
    panel_admin.has_data_limit = new_limit_bytes > 0
    panel_admin.admin_remaining = max(0, new_limit_bytes - panel_admin.admin_used_bytes)
    panel_admin.save(update_fields=['admin_limit_bytes', 'has_data_limit', 'admin_remaining'])

    from .ledger import record_quota_charge
    record_quota_charge(username, current_limit, new_limit_bytes, by=by)

    new_gb = new_limit_bytes / gb
    label = "Unlimited" if new_limit_bytes <= 0 else (
        f"{new_gb:.0f} GB" if new_gb < 1000 else f"{new_gb / 1000:.1f} TB"
    )
    return True, f"Limit set to {label} — {message}"


def remove_limit(username: str) -> tuple[bool, str]:
    """PAMP remove_limit: unlimited on the panel."""
    _gate()
    from .panel_api import PanelAPIClient

    panel_admin = get_object_or_404(PanelAdmin, username=username)
    client = PanelAPIClient()
    client.authenticate()

    success, message = client.set_admin_data_limit(username, 0)
    if not success:
        return False, f"Failed: {message}"

    panel_admin.admin_limit_bytes = 0
    panel_admin.has_data_limit = False
    panel_admin.admin_remaining = 0
    panel_admin.save(update_fields=['admin_limit_bytes', 'has_data_limit', 'admin_remaining'])
    return True, f"{message} — admin is now unlimited"


def admin_action(username: str, action: str) -> tuple[bool, str]:
    """PAMP admin_action: disable_admin | enable_admin | disable_users | enable_users."""
    _gate()
    from .panel_api import PanelAPIClient

    panel_admin = get_object_or_404(PanelAdmin, username=username)
    client = PanelAPIClient()
    client.authenticate()

    if action == 'disable_admin':
        success, message = client.disable_admin(username)
        if success:
            panel_admin.status = 'disabled'
            panel_admin.is_active = False
            panel_admin.save(update_fields=['status', 'is_active'])
            return True, message
        return False, f"Failed to disable: {message}"

    elif action == 'enable_admin':
        success, message = client.enable_admin(username)
        if success:
            panel_admin.status = 'active'
            panel_admin.is_active = True
            panel_admin.save(update_fields=['status', 'is_active'])
            return True, message
        return False, f"Failed to enable: {message}"

    elif action == 'disable_users':
        success, message = client.disable_all_users(username)
        if success:
            panel_admin.active_user_count = 0
            panel_admin.disabled_users = panel_admin.user_count
            panel_admin.save(update_fields=['active_user_count', 'disabled_users'])
            return True, message
        return False, f"Failed: {message}"

    elif action == 'enable_users':
        success, message = client.enable_all_users(username)
        if success:
            return True, message
        return False, f"Failed: {message}"

    return False, "Unknown action"


def reset_deleted_traffic(username: str) -> tuple[bool, str]:
    """PAMP reset_deleted_traffic: the deleted-users counter back to 0."""
    _gate()
    panel_admin = get_object_or_404(PanelAdmin, username=username)
    panel_admin.deleted_users_used_bytes = 0
    panel_admin.deleted_traffic_reset_at = timezone.now()
    panel_admin.save(update_fields=['deleted_users_used_bytes', 'deleted_traffic_reset_at'])
    return True, "Deleted-users counter reset to 0"


def sync_now() -> tuple[bool, str]:
    """PAMP trigger_sync: run the sync synchronously."""
    _gate()
    from .tasks import sync_panel_admins

    result = sync_panel_admins.apply(throw=False)
    if result.failed():
        return False, f"Sync failed: {str(result.result)[:120]}"
    return True, str(result.result)


def save_group(owner: str, members: str, note: str) -> tuple[bool, str]:
    """PAMP save_account_group."""
    _gate()
    owner = (owner or '').strip()
    if not owner:
        return False, "Owner username is required"
    _, created = AdminGroup.objects.update_or_create(
        owner_username=owner,
        defaults={'member_usernames': (members or '').strip(), 'note': (note or '').strip()},
    )
    return True, f"Group {'created' if created else 'updated'} for {owner}"


def delete_group(group_id: int) -> tuple[bool, str]:
    """PAMP delete_account_group."""
    _gate()
    AdminGroup.objects.filter(id=group_id).delete()
    return True, "Group deleted"
