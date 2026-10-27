"""Create / edit / delete PasarGuard admins from the Agency panel (caspintunel
addition — not part of the PAMP port, whose files stay verbatim).

Field list taken from the live panel's OpenAPI schema (PasarGuard 5.4.1,
`AdminCreate` / `AdminModify`): username, password, role_id (required on
create — 5.4 replaced `is_sudo` with roles; owner roles are the old "sudo"),
telegram_id, discord_webhook, status, data_limit, sub_template, sub_domain,
profile_title, support_url, custom_variables[{key, value}], note,
notification_enable{…7 booleans}, permission_overrides{…RoleLimits}.
Allowed groups / user templates are properties of the ROLE in 5.4 (RoleAccess),
so they are shown with the roles, read live from the panel.

Rule (as everywhere): panel first, then read the admin back. Every action is
audited by the view; the cut-over gate applies to every write.
"""
from __future__ import annotations

import re
import secrets
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django.db import transaction

from apps.panel.client import PasarGuardClient
from apps.panel.exceptions import PanelConflict, PanelError, PanelNotFound, PanelValidationError

from .actions import _gate
from .models import AdminGroup, PanelAdmin

GB = 1024 ** 3
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.@-]{3,32}$")
NOTIFY_KEYS = ["create", "modify", "delete", "status_change", "reset_data_usage", "data_reset_by_next", "subscription_revoked"]
LIMIT_KEYS = ["max_users", "data_limit_min", "data_limit_max", "expire_min", "expire_max", "min_hwid_per_user",
              "max_hwid_per_user", "on_hold_timeout_min", "on_hold_timeout_max"]
TEXT_KEYS = {"discord_webhook": 512, "sub_template": 255, "sub_domain": 255, "profile_title": 255, "support_url": 512,
             "note": 1000}
STATUSES = ("active", "disabled")


class AdminCrudError(ValueError):
    def __init__(self, message: str, code: str = "invalid", field: str | None = None):
        super().__init__(message)
        self.code, self.field = code, field


# --- panels ----------------------------------------------------------------------
def panels() -> list:
    from apps.panel.models import Panel

    return list(Panel.objects.filter(is_active=True).order_by("id"))


def panel_for(panel_id=None):
    from .panel_api import agency_panel

    if panel_id in (None, "", "null"):
        return agency_panel()
    from apps.panel.models import Panel

    p = Panel.objects.filter(pk=panel_id, is_active=True).first()
    if p is None:
        raise AdminCrudError("unknown panel", "panel", "panel")
    return p


def is_agency_panel(panel) -> bool:
    from .panel_api import agency_panel

    try:
        return agency_panel().id == panel.id
    except Exception:  # noqa: BLE001
        return False


def generate_password(length: int = 16) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if any(c.isdigit() for c in pw) and any(c.isupper() for c in pw) and any(c.islower() for c in pw):
            return pw


def _err(exc: PanelError) -> AdminCrudError:
    body = getattr(exc, "body", "") or ""
    detail = ""
    try:
        import json

        j = json.loads(body)
        detail = j.get("detail") if isinstance(j, dict) else ""
        if isinstance(detail, list):
            detail = "; ".join(f"{'.'.join(str(x) for x in d.get('loc', [])[1:])}: {d.get('msg')}" for d in detail)
    except Exception:  # noqa: BLE001
        detail = body[:200]
    if isinstance(exc, PanelConflict):
        return AdminCrudError("an admin with this username already exists on the panel", "exists", "username")
    if isinstance(exc, PanelNotFound):
        return AdminCrudError("admin not found on the panel", "not_found")
    if isinstance(exc, PanelValidationError):
        return AdminCrudError(f"the panel refused it: {detail or exc}", "panel_refused")
    return AdminCrudError(f"panel error: {exc}", "panel_error")


# --- live options (roles + what each role allows) ---------------------------------
def options(panel) -> dict:
    c = PasarGuardClient(panel)
    try:
        roles = (c._request("GET", "/api/admin-roles/simple") or {}).get("roles", [])
        groups = {g["id"]: g["name"] for g in (c._request("GET", "/api/groups/simple") or {}).get("groups", [])}
        try:
            templates = {t["id"]: t["name"] for t in (c._request("GET", "/api/user_templates/simple") or {}).get("templates", [])}
        except PanelError:
            templates = {}
        out = []
        for r in roles:
            try:
                full = c._request("GET", f"/api/admin-role/{int(r['id'])}") or {}
            except PanelError:
                full = {}
            access = full.get("access") or {}
            out.append({
                "id": r["id"], "name": r.get("name", ""), "is_owner": bool(r.get("is_owner")),
                "groups": [groups.get(i, f"#{i}") for i in (access.get("allowed_group_ids") or [])],
                "templates": [templates.get(i, f"#{i}") for i in (access.get("allowed_template_ids") or [])],
                "all_groups": access.get("allowed_group_ids") is None,
                "limits": {k: v for k, v in (full.get("limits") or {}).items() if v is not None},
            })
    except PanelError as exc:
        raise _err(exc) from exc
    return {"roles": out, "groups": [{"id": k, "name": v} for k, v in groups.items()],
            "notify_keys": NOTIFY_KEYS, "limit_keys": LIMIT_KEYS, "statuses": list(STATUSES)}


def get_admin(panel, username: str) -> dict:
    c = PasarGuardClient(panel)
    try:
        data = c._request("GET", "/api/admins", params={"username": username, "limit": 5}) or {}
    except PanelError as exc:
        raise _err(exc) from exc
    rows = data.get("admins", data) if isinstance(data, dict) else data
    for a in rows or []:
        if a.get("username") == username:
            return a
    raise AdminCrudError("admin not found on the panel", "not_found")


def editable_view(a: dict) -> dict:
    """What the Settings tab edits (never the password)."""
    role = a.get("role") or {}
    return {
        "username": a.get("username"), "role_id": role.get("id"), "role_name": role.get("name"),
        "is_owner": bool(role.get("is_owner")), "status": "disabled" if a.get("is_disabled") else a.get("status", "active"),
        "telegram_id": a.get("telegram_id"), "discord_webhook": a.get("discord_webhook") or "",
        "sub_template": a.get("sub_template") or "", "sub_domain": a.get("sub_domain") or "",
        "profile_title": a.get("profile_title") or "", "support_url": a.get("support_url") or "",
        "note": a.get("note") or "", "custom_variables": a.get("custom_variables") or [],
        "notification_enable": a.get("notification_enable") or {k: True for k in NOTIFY_KEYS},
        "permission_overrides": a.get("permission_overrides") or {}, "data_limit": a.get("data_limit"),
        "total_users": a.get("total_users"), "used_traffic": a.get("used_traffic"),
    }


# --- payload validation -----------------------------------------------------------
def _int_or_none(v, field):
    if v in (None, ""):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        raise AdminCrudError(f"{field} must be a whole number", "invalid", field)


def build_payload(data: dict, *, creating: bool) -> dict:
    """Validate the form → the PasarGuard AdminCreate / AdminModify body. Only keys
    present in `data` are sent on modify."""
    p: dict = {}
    if creating:
        username = str(data.get("username") or "").strip()
        if not USERNAME_RE.match(username):
            raise AdminCrudError("username: 3–32 letters, digits or _ . @ -", "username", "username")
        p["username"] = username
    if "password" in data and data.get("password") not in (None, ""):
        pw = str(data["password"])
        if len(pw) < 8:
            raise AdminCrudError("password: at least 8 characters", "password", "password")
        p["password"] = pw
    elif creating:
        raise AdminCrudError("password is required", "password", "password")
    if "role_id" in data or creating:
        rid = _int_or_none(data.get("role_id"), "role_id")
        if rid is None and creating:
            raise AdminCrudError("pick a role", "role", "role_id")
        if rid is not None:
            p["role_id"] = rid
    if "telegram_id" in data:
        p["telegram_id"] = _int_or_none(data.get("telegram_id"), "telegram_id")
    if "status" in data and data.get("status"):
        if data["status"] not in STATUSES:
            raise AdminCrudError("status must be active or disabled", "invalid", "status")
        p["status"] = data["status"]
    for k, maxlen in TEXT_KEYS.items():
        if k in data:
            v = str(data.get(k) or "").strip()
            if len(v) > maxlen:
                raise AdminCrudError(f"{k}: at most {maxlen} characters", "invalid", k)
            if k in ("discord_webhook", "support_url") and v and not v.startswith(("https://", "http://")):
                raise AdminCrudError(f"{k} must be a http(s) URL", "invalid", k)
            p[k] = v or None
    if "custom_variables" in data:
        cv = []
        for item in data.get("custom_variables") or []:
            key = str((item or {}).get("key") or "").strip()
            if not key:
                continue
            if len(key) > 64 or len(str(item.get("value") or "")) > 512:
                raise AdminCrudError("custom variable too long (key 64, value 512)", "invalid", "custom_variables")
            cv.append({"key": key, "value": str(item.get("value") or "")})
        p["custom_variables"] = cv
    if "notification_enable" in data and isinstance(data["notification_enable"], dict):
        p["notification_enable"] = {k: bool(data["notification_enable"].get(k, True)) for k in NOTIFY_KEYS}
    if "permission_overrides" in data and isinstance(data["permission_overrides"], dict):
        po = {k: _int_or_none(data["permission_overrides"].get(k), k) for k in LIMIT_KEYS}
        p["permission_overrides"] = po if any(v is not None for v in po.values()) else None
    return p


def _limit_bytes(data: dict) -> int:
    """Initial limit: value + unit (GB / TB); 0 / empty = unlimited."""
    raw = data.get("limit_value")
    if raw in (None, ""):
        return 0
    try:
        v = Decimal(str(raw))
    except InvalidOperation:
        raise AdminCrudError("limit must be a number", "invalid", "limit_value")
    if v < 0:
        raise AdminCrudError("limit must be positive", "invalid", "limit_value")
    mult = 1024 if str(data.get("limit_unit") or "GB").upper() == "TB" else 1
    return int(v * mult * GB)


# --- actions ----------------------------------------------------------------------
def create(panel, data: dict, *, by: str = "") -> dict:
    """Create the admin on the panel, then (optionally) price + quota charge + group.
    Returns the "send to reseller" card data (the password only this once)."""
    _gate()
    payload = build_payload(data, creating=True)
    limit = _limit_bytes(data)
    payload["data_limit"] = limit or 0
    price = data.get("price_per_gb")
    if price not in (None, ""):
        try:
            price = Decimal(str(price))
        except InvalidOperation:
            raise AdminCrudError("price per GB must be a number", "invalid", "price_per_gb")
        if price < 0:
            raise AdminCrudError("price per GB must be positive", "invalid", "price_per_gb")
    group = None
    if data.get("group_id"):
        group = AdminGroup.objects.filter(pk=data["group_id"]).first()
        if group is None:
            raise AdminCrudError("unknown group", "invalid", "group_id")
    c = PasarGuardClient(panel)
    try:
        c._request("POST", "/api/admin", json=payload)
        created = get_admin(panel, payload["username"])          # read back
    except PanelError as exc:
        raise _err(exc) from exc

    username = payload["username"]
    tracked = is_agency_panel(panel)
    charge = None
    if tracked:
        with transaction.atomic():
            # the next sync fills every PAMP counter; the row exists now so the detail page works
            PanelAdmin.objects.get_or_create(
                username=username,
                defaults={"has_data_limit": limit > 0, "admin_limit_bytes": limit, "admin_remaining": limit,
                          "last_limit_bytes": limit,
                          "status": "active" if payload.get("status", "active") == "active" else "disabled",
                          "is_active": payload.get("status", "active") == "active",
                          "raw_data": created})
            from . import ledger

            if price is not None:
                ledger.set_price(username, price, ledger.today(), note="set on creation", by=by)
            entry = None
            if limit > 0:
                entry = ledger.record_quota_charge(username, 0, limit, by=by)
                charge = {"amount": str(entry.amount), "gb": str(entry.gb)} if entry else None
            from . import limit_history

            limit_history.record(username, None, limit, action="create", source="panel", by=by,
                                 note="admin created", ledger_entry=entry)
            if group is not None:
                from . import groups as G

                members = G._members(group.member_usernames) + [username]
                G.upsert(group.id, owner=group.owner_username, members=members, name=group.name, note=group.note)
    return {"username": username, "password": payload["password"], "panel": panel.name, "tracked": tracked,
            "limit_bytes": limit, "charge": charge, "group": group.name or group.owner_username if group else None,
            "admin": editable_view(created)}


def modify(panel, username: str, data: dict) -> dict:
    _gate()
    payload = build_payload(data, creating=False)
    if not payload:
        raise AdminCrudError("nothing to change", "empty")
    c = PasarGuardClient(panel)
    try:
        c._request("PUT", f"/api/admin/{quote(username, safe='')}", json=payload)
        a = get_admin(panel, username)
    except PanelError as exc:
        raise _err(exc) from exc
    if is_agency_panel(panel) and "status" in payload:
        PanelAdmin.objects.filter(username=username).update(
            status="active" if payload["status"] == "active" else "disabled", is_active=payload["status"] == "active")
    return {"changed": sorted(k for k in payload if k != "password"), "password_changed": "password" in payload,
            "admin": editable_view(a)}


def delete(panel, username: str, typed: str) -> None:
    _gate()
    if (typed or "").strip() != username:
        raise AdminCrudError("type the admin's username exactly to confirm", "confirm", "confirm")
    c = PasarGuardClient(panel)
    try:
        c._request("DELETE", f"/api/admin/{quote(username, safe='')}")
    except PanelNotFound:
        pass                                   # already gone on the panel — clean up here too
    except PanelError as exc:
        raise _err(exc) from exc
    if is_agency_panel(panel):
        # ledger lines and prices stay (accounting history); groups lose the member
        PanelAdmin.objects.filter(username=username).delete()
        from . import groups as G

        for g in AdminGroup.objects.all():
            if g.owner_username == username:          # a group without its owner has no meaning
                g.delete()
                continue
            names = G._members(g.member_usernames)
            if username in names:
                G.upsert(g.id, owner=g.owner_username, members=[n for n in names if n != username], name=g.name,
                         note=g.note)
