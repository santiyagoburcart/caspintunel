"""Group managers (caspintunel addition) — docs/agency.md → "Group managers".

Staff create any number of managers and assign each one or more agency groups
(AdminGroup), with the PasarGuard roles it may give per group. In PasarGuard 5.4
an admin's inbounds come from its ROLE (RoleAccess.allowed_group_ids), so "allowed
inbounds" = allowed roles, shown with the inbound groups each one opens. Owner
roles are never allowed.

Since v1.25 a manager signs in to /panel/ as a staff account (GroupManager.staff,
RBAC role "Group manager", same username/password). A linked staff is default-denied
on every admin API (adminpanel.permissions.StaffPermission) and reaches only
/api/v1/agency/manager/* (manager_views.py, IsGroupManagerStaff). What a manager may
do, all scoped to the admins of its own groups:
  * create a PasarGuard admin (allowed role, initial GB > 0) — live at once;
  * add volume (increase only) — live at once;
  * change an admin's password and role (allowed list only);
  * read accounting (statements, balances, pending, group statement).
Every volume a manager gives becomes a VolumeRequest ("pending approval"); staff
approve it (→ quota charge in the ledger, linked in the limit history) or reject
it (→ the volume is taken back on PasarGuard, no charge). Never: reduce / remove
a limit, unlimited, delete admins, owner roles, payments, prices, other groups.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from urllib.parse import quote

from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.common.models import AuditLog, write_audit

from .models import (AdminGroup, AdminLimitChange, GroupManager, GroupManagerAssignment, LedgerEntry, ManagerSession,
                     PanelAdmin, VolumeRequest)

GB = 1024 ** 3
D0 = Decimal(0)
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.@-]{3,64}$")
MAX_GB = Decimal(1_000_000)
ROLES_CACHE = "agency:mgr:roles"


class ManagerError(Exception):
    """code → HTTP status in views (STATUS)."""

    STATUS = {"forbidden": 403, "not_found": 404, "cap_reached": 409, "exists": 409, "pre_cutover": 409,
              "unlimited_now": 409, "not_pending": 409, "no_price": 409, "busy": 409,
              "panel_error": 502, "panel_refused": 502}

    def __init__(self, message: str, code: str = "invalid", field: str | None = None, **extra):
        super().__init__(message)
        self.code, self.field, self.extra = code, field, extra

    @property
    def status(self) -> int:
        return self.STATUS.get(self.code, 400)

    def payload(self) -> dict:
        return {"detail": str(self), "code": self.code, "field": self.field, **self.extra}


def forbidden(msg: str = "a group manager cannot do this") -> ManagerError:
    return ManagerError(msg, "forbidden")


def label(m: GroupManager) -> str:
    return f"manager:{m.username}"


def _gate():
    from .actions import PreCutover, _gate as gate

    try:
        gate()
    except PreCutover as exc:
        raise ManagerError(str(exc), "pre_cutover") from exc


def _gb(value, field="gb") -> Decimal:
    try:
        v = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise ManagerError("enter the volume in GB", "invalid", field)
    if v.is_nan() or v.is_infinite():
        raise ManagerError("enter the volume in GB", "invalid", field)
    return v


def _panel():
    from .panel_api import PanelAPIError, agency_panel

    try:
        return agency_panel()
    except PanelAPIError as exc:
        raise ManagerError(str(exc), "panel_error") from exc


def _client():
    from apps.panel.client import PasarGuardClient

    return PasarGuardClient(_panel())


def _panel_err(exc) -> ManagerError:
    from .admin_crud import _err

    e = _err(exc)
    return ManagerError(str(e), e.code, e.field)


# ------------------------------------------------------------------ roles (= inbound sets)
def roles_catalog(fresh: bool = False) -> dict[int, dict]:
    """PasarGuard roles with the inbound groups each one opens, read live (cached 5 min)."""
    if not fresh:
        hit = cache.get(ROLES_CACHE)
        if hit is not None:
            return hit
    from .admin_crud import AdminCrudError, options

    try:
        opts = options(_panel())
    except AdminCrudError as exc:
        raise ManagerError(str(exc), "panel_error") from exc
    cat = {int(r["id"]): {"id": int(r["id"]), "name": r["name"], "is_owner": r["is_owner"],
                          "inbounds": r["groups"], "all_inbounds": r["all_groups"]} for r in opts["roles"]}
    cache.set(ROLES_CACHE, cat, 300)
    return cat


def _role_view(rid: int, cat: dict | None) -> dict:
    r = (cat or {}).get(int(rid))
    return r or {"id": int(rid), "name": f"#{rid}", "is_owner": False, "inbounds": [], "all_inbounds": False}


def _safe_catalog() -> dict | None:
    try:
        return roles_catalog()
    except ManagerError:
        return None


# ------------------------------------------------------------------ staff: managers
def _clean_assignments(raw, cat_needed=True) -> list[tuple[AdminGroup, list[int]]]:
    out, seen = [], set()
    for item in raw or []:
        try:
            gid = int((item or {}).get("group_id"))
        except (TypeError, ValueError):
            raise ManagerError("unknown group", "invalid", "assignments")
        if gid in seen:
            continue
        seen.add(gid)
        g = AdminGroup.objects.filter(pk=gid).first()
        if g is None:
            raise ManagerError(f"unknown group #{gid}", "invalid", "assignments")
        try:
            rids = sorted({int(x) for x in (item.get("role_ids") or [])})
        except (TypeError, ValueError):
            raise ManagerError("role ids must be numbers", "invalid", "assignments")
        out.append((g, rids))
    if cat_needed and any(r for _, r in out):
        cat = roles_catalog(fresh=True)
        for _, rids in out:
            for rid in rids:
                if rid not in cat:
                    raise ManagerError(f"role #{rid} is not on the panel", "invalid", "assignments")
                if cat[rid]["is_owner"]:
                    raise ManagerError(f"role “{cat[rid]['name']}” is an owner role — never allowed", "invalid", "assignments")
    return out


def _cap(value):
    if value in (None, ""):
        return None
    v = _gb(value, "max_unapproved_gb")
    if v < 0:
        raise ManagerError("the cap must be zero or more", "invalid", "max_unapproved_gb")
    return v


@transaction.atomic
def save_manager(manager_id: int | None, data: dict, by: str = "") -> GroupManager:
    m = GroupManager.objects.select_for_update().filter(pk=manager_id).first() if manager_id else None
    if manager_id and m is None:
        raise ManagerError("manager not found", "not_found")
    if m is None:
        username = str(data.get("username") or "").strip()
        if not USERNAME_RE.match(username):
            raise ManagerError("username: 3–64 letters, digits or _ . @ -", "invalid", "username")
        if GroupManager.objects.filter(username__iexact=username).exists():
            raise ManagerError("a group manager with this username exists", "exists", "username")
        existing = _staff_model().objects.filter(username__iexact=username).first()
        if existing is not None and not _linkable(existing):
            raise ManagerError("a panel (staff) account with this username exists", "exists", "username")
        pw = str(data.get("password") or "")
        if existing is not None and not pw:
            # v1.25.2: an existing staff with the "Group manager" role keeps its own password
            m = GroupManager(username=existing.username, password=existing.password_hash, created_by=by[:150])
        else:
            if len(pw) < 8:
                raise ManagerError("password: at least 8 characters", "invalid", "password")
            m = GroupManager(username=username, password=make_password(pw), created_by=by[:150])
    if "display_name" in data:
        m.display_name = str(data.get("display_name") or "").strip()[:100]
    if "note" in data:
        m.note = str(data.get("note") or "").strip()[:255]
    if "max_unapproved_gb" in data:
        m.max_unapproved_gb = _cap(data.get("max_unapproved_gb"))
    was_active = m.is_active if m.pk else True
    if "is_active" in data:
        m.is_active = bool(data.get("is_active"))
    assignments = _clean_assignments(data["assignments"]) if "assignments" in data else None
    m.save()
    if assignments is not None:
        _apply_assignments(m, assignments)
    _sync_staff(m, password=(str(data.get("password") or "") or None) if manager_id is None else None)
    if was_active and not m.is_active:
        revoke_sessions(m)
    return m


def _staff_model():
    from apps.accounts.models import Staff

    return Staff


def gm_role():
    from apps.accounts.models import GROUP_MANAGER_PERM, GROUP_MANAGER_ROLE, Permission, Role

    perm, _ = Permission.objects.get_or_create(
        code=GROUP_MANAGER_PERM, defaults={"name": "Group manager: own groups only (agency admins, volume, accounting)",
                                           "name_fa": "مدیر گروه: فقط گروه‌های خودش (ادمین‌های نماینده، حجم، حسابداری)"})
    role, created = Role.objects.get_or_create(name=GROUP_MANAGER_ROLE,
                                               defaults={"description": "Group managers — own agency groups only",
                                                         "name_fa": "مدیر گروه",
                                                         "description_fa": "مدیران گروه — فقط گروه‌های نمایندگی خودشان"})
    if created:
        from apps.accounts.models import GM_PERMS

        abilities = [Permission.objects.get_or_create(code=c, defaults={"name": en, "name_fa": fa})[0]
                     for c, (en, fa) in GM_PERMS.items()]
        role.permissions.set([perm, *abilities])          # v1.27: a new role can do everything until narrowed
    if not role.name_fa or not role.description_fa:          # Persian labels (v1.25.2) — never overwrite an edit
        Role.objects.filter(pk=role.pk, name_fa="").update(name_fa="مدیر گروه")
        Role.objects.filter(pk=role.pk, description_fa="").update(description_fa="مدیران گروه — فقط گروه‌های نمایندگی خودشان")
        role.refresh_from_db(fields=["name_fa", "description_fa"])
    return role


def _sync_staff(m: GroupManager, password: str | None = None):
    """Keep the manager's /panel/ staff account in step (created on first save; a taken
    staff username is never linked — the manager then stays without a panel login)."""
    Staff = _staff_model()
    s = m.staff
    if s is None:
        found = Staff.objects.filter(username__iexact=m.username).first()
        if found is not None:
            if not _linkable(found):
                return
            s = found                              # v1.25.2: staff made on the Staff page first
            if password:
                s.set_password(password)
        else:
            s = Staff(username=m.username, role=gm_role(), is_superadmin=False)
            if password:
                s.set_password(password)
            else:
                s.password_hash = m.password       # same Django hasher format
    s.is_active = m.is_active
    s.display_name = (m.display_name or "")[:60]
    s.save()
    if m.staff_id != s.pk:
        m.staff = s
        GroupManager.objects.filter(pk=m.pk).update(staff=s)


def _apply_assignments(m: GroupManager, assignments: list[tuple[AdminGroup, list[int]]]) -> None:
    keep = []
    for g, rids in assignments:
        a, _ = GroupManagerAssignment.objects.update_or_create(manager=m, group=g, defaults={"allowed_role_ids": rids})
        keep.append(a.pk)
    GroupManagerAssignment.objects.filter(manager=m).exclude(pk__in=keep).delete()


def is_gm_role(role) -> bool:
    """The RBAC role that makes a staff a group manager ("Group manager", or any role
    holding the agency.group_manager permission)."""
    from apps.accounts.models import GROUP_MANAGER_PERM, GROUP_MANAGER_ROLE

    if role is None:
        return False
    return role.name == GROUP_MANAGER_ROLE or role.permissions.filter(code=GROUP_MANAGER_PERM).exists()


def _linkable(staff) -> bool:
    """A staff account a group manager may be attached to: has the role, is not a
    superadmin and is not linked to another manager yet."""
    return (not staff.is_superadmin and is_gm_role(staff.role)
            and not GroupManager.objects.filter(staff=staff).exists())


@transaction.atomic
def sync_from_staff(staff, data: dict | None = None, by: str = "") -> GroupManager | None:
    """Staff page → group manager (v1.25.2), the mirror of `_sync_staff`.

    * staff with the "Group manager" role (not superadmin) always has a linked
      GroupManager: the existing link, else an unlinked manager of the same
      username, else a new one (same password hash, no groups yet);
    * `data` (optional) = {"assignments": [{group_id, role_ids}], "max_unapproved_gb"}
      — the same rules as Agency → Group managers (`_clean_assignments`, `_cap`);
    * a staff that loses the role (or becomes superadmin) is unlinked: the manager
      is disabled and keeps its history (requests, activity)."""
    m = GroupManager.objects.select_for_update().filter(staff=staff).first()
    wants = not staff.is_superadmin and is_gm_role(staff.role)
    if not wants:
        if data and (data.get("assignments") or data.get("max_unapproved_gb") not in (None, "")):
            raise ManagerError("only a staff account with the “Group manager” role can have groups",
                               "invalid", "group_manager")
        if m is not None:
            GroupManager.objects.filter(pk=m.pk).update(staff=None, is_active=False, updated_at=timezone.now())
            ManagerSession.objects.filter(manager=m, revoked=False).update(revoked=True)
            write_audit(action="agency.manager.unlinked", staff=by or "staff page", target=m,
                        detail={"manager": m.username, "staff": staff.username, "reason": "role removed"})
        staff._state.fields_cache.pop("group_manager", None)    # the reverse one-to-one is cached
        return None
    if m is None:
        m = GroupManager.objects.select_for_update().filter(username__iexact=staff.username, staff__isnull=True).first()
        if m is None:
            if GroupManager.objects.filter(username__iexact=staff.username).exists():
                raise ManagerError("a group manager with this username is linked to another panel account",
                                   "exists", "group_manager")
            m = GroupManager(username=staff.username, created_by=by[:150])
    m.staff = staff
    m.password = staff.password_hash
    m.is_active = staff.is_active
    if staff.display_name:
        m.display_name = staff.display_name[:100]
    if data and "max_unapproved_gb" in data:
        m.max_unapproved_gb = _cap(data.get("max_unapproved_gb"))
    m.save()
    staff._state.fields_cache["group_manager"] = m
    if data and "assignments" in data:
        _apply_assignments(m, _clean_assignments(data["assignments"]))
    return m


def staff_info(staff) -> dict | None:
    """What the Staff page shows for a group-manager staff (None for everyone else)."""
    m = staff.group_manager_row
    if m is None:
        if staff.is_superadmin or not is_gm_role(staff.role):
            return None
        return {"id": None, "assignments": [], "max_unapproved_gb": None, "warnings": ["no_group"]}
    rows = [{"group_id": a.group_id, "group": group_title(a.group), "role_ids": a.allowed_role_ids}
            for a in m.assignments.select_related("group").order_by("group__owner_username")]
    return {"id": m.id, "assignments": rows, "max_unapproved_gb": m.max_unapproved_gb, "warnings": warnings(m, rows)}


def warnings(m: GroupManager, rows: list | None = None) -> list[str]:
    rows = rows if rows is not None else list(m.assignments.all())
    out = []
    if not rows:
        out.append("no_group")
    elif any(not (r["role_ids"] if isinstance(r, dict) else r.allowed_role_ids) for r in rows):
        out.append("no_role")
    if not m.staff_id:
        out.append("no_login")
    return out


def options_payload() -> dict:
    """Agency groups + PasarGuard roles (owner roles left out) for the assignment pickers."""
    try:
        cat = roles_catalog(fresh=True)
        roles = [r for r in cat.values() if not r["is_owner"]]
        err = None
    except ManagerError as exc:
        roles, err = [], str(exc)
    return {
        "groups": [{"id": g.id, "name": group_title(g), "owner": g.owner_username, "admins": len(g.get_all_usernames())}
                   for g in AdminGroup.objects.order_by("owner_username")],
        "roles": sorted(roles, key=lambda r: r["id"]), "roles_error": err,
    }


def set_password(m: GroupManager, password: str | None = None) -> str:
    from .admin_crud import generate_password

    pw = str(password or "") or generate_password()
    if len(pw) < 8:
        raise ManagerError("password: at least 8 characters", "invalid", "password")
    m.password = make_password(pw)
    m.save(update_fields=["password", "updated_at"])
    if m.staff_id:
        m.staff.set_password(pw)               # also ends its panel sessions (token_version)
        m.staff.save(update_fields=["password_hash", "token_version", "updated_at"])
    else:
        _sync_staff(m, password=pw)
    revoke_sessions(m)
    return pw


def revoke_sessions(m: GroupManager) -> int:
    """End the manager's panel sessions (staff token_version) and any pre-v1.25 portal session."""
    if m.staff_id:
        Staff = _staff_model()
        Staff.objects.filter(pk=m.staff_id).update(token_version=models.F("token_version") + 1)
    return ManagerSession.objects.filter(manager=m, revoked=False).update(revoked=True)


def pending_gb(m: GroupManager) -> Decimal:
    return VolumeRequest.objects.filter(manager=m, status="pending").aggregate(s=Sum("gb"))["s"] or D0


def cap_state(m: GroupManager) -> dict:
    used = pending_gb(m)
    cap = m.max_unapproved_gb
    return {"max_gb": cap, "pending_gb": used, "left_gb": None if cap is None else max(D0, cap - used),
            "reached": cap is not None and used >= cap}


def manager_row(m: GroupManager, cat: dict | None = None) -> dict:
    return {
        "id": m.id, "username": m.username, "display_name": m.display_name, "is_active": m.is_active, "note": m.note,
        "max_unapproved_gb": m.max_unapproved_gb, "created_by": m.created_by, "created_at": m.created_at,
        "last_login_at": (m.staff.last_login if m.staff_id else None) or m.last_login_at, "cap": cap_state(m),
        "pending_count": VolumeRequest.objects.filter(manager=m, status="pending").count(),
        # v1.25: the manager signs in to /panel/ as this staff account (None = username taken by other staff)
        "staff_username": m.staff.username if m.staff_id else None,
        "warnings": warnings(m),
        "assignments": [{"group_id": a.group_id, "group": group_title(a.group), "role_ids": a.allowed_role_ids,
                         "roles": [_role_view(r, cat) for r in a.allowed_role_ids]}
                        for a in m.assignments.select_related("group").order_by("group__owner_username")],
    }


def group_title(g: AdminGroup | None) -> str:
    return "" if g is None else (g.name or g.owner_username)


# ------------------------------------------------------------------ scope
def assignments(m: GroupManager) -> list[GroupManagerAssignment]:
    return list(m.assignments.select_related("group").order_by("group__owner_username"))


def assignment_for_group(m: GroupManager, group_id) -> GroupManagerAssignment:
    try:
        gid = int(group_id)
    except (TypeError, ValueError):
        raise forbidden("not your group")
    a = m.assignments.select_related("group").filter(group_id=gid).first()
    if a is None:
        raise forbidden("not your group")
    return a


def assignment_for_admin(m: GroupManager, username: str) -> GroupManagerAssignment:
    for a in assignments(m):
        if username in a.group.get_all_usernames():
            return a
    raise forbidden("this admin is not in your groups")


def visible_usernames(m: GroupManager) -> list[str]:
    out = []
    for a in assignments(m):
        for u in a.group.get_all_usernames():
            if u not in out:
                out.append(u)
    return out


def _audit(m: GroupManager, action: str, a: GroupManagerAssignment | None, **detail):
    write_audit(action=f"agency.manager.{action}", staff=label(m), detail={
        "manager": m.username, "group_id": a.group_id if a else None, "group": group_title(a.group) if a else "", **detail})


def _from_crud(exc) -> ManagerError:
    extra = {"detail_fa": exc.message_fa} if getattr(exc, "message_fa", None) else {}
    return ManagerError(str(exc), exc.code, exc.field, **extra)


def _writable_admin(m: GroupManager, username: str) -> tuple[GroupManagerAssignment, dict]:
    """The admin must be in the manager's groups and must not hold an owner role; returns
    (assignment, live PasarGuard admin)."""
    from .admin_crud import AdminCrudError, get_admin

    a = assignment_for_admin(m, username)
    pa = PanelAdmin.objects.filter(username=username).first()
    if pa is not None and pa.is_sudo:
        raise forbidden("owner (sudo) admins are managed by staff only")
    try:
        live = get_admin(_panel(), username)
    except AdminCrudError as exc:
        raise ManagerError(str(exc), exc.code) from exc
    if (live.get("role") or {}).get("is_owner"):
        raise forbidden("owner (sudo) admins are managed by staff only")
    return a, live


def _check_role(a: GroupManagerAssignment, role_id) -> int:
    try:
        rid = int(role_id)
    except (TypeError, ValueError):
        raise ManagerError("pick the inbounds", "invalid", "role_id")
    if rid not in [int(x) for x in a.allowed_role_ids]:
        raise forbidden("these inbounds are not allowed for this group")
    cat = roles_catalog()
    if rid not in cat or cat[rid]["is_owner"]:
        raise forbidden("these inbounds are not allowed for this group")
    return rid


def _check_cap(m: GroupManager, gb: Decimal):
    if m.max_unapproved_gb is None:
        return
    used = pending_gb(m)
    if used + gb > m.max_unapproved_gb:
        raise ManagerError("your unapproved volume cap is reached — new volume waits until staff approve",
                           "cap_reached", "gb", cap_gb=str(m.max_unapproved_gb), pending_gb=str(used),
                           left_gb=str(max(D0, m.max_unapproved_gb - used)))


def _positive_gb(value) -> Decimal:
    gb = _gb(value)
    if gb <= 0:
        # 0 = unlimited on PasarGuard, negative = a reduction: both are staff-only
        raise forbidden("only a positive volume can be given (no reduce, no unlimited)")
    if gb > MAX_GB:
        raise ManagerError("volume too large", "invalid", "gb")
    return gb


class _AdminLock:
    """One manager write per admin at a time (double taps, two tabs)."""

    def __init__(self, username: str):
        self.key = "agency:mgr:lock:" + hashlib.sha256(username.encode()).hexdigest()[:24]

    def __enter__(self):
        if not cache.add(self.key, 1, 60):
            raise ManagerError("another change for this admin is running — try again in a moment", "busy")
        return self

    def __exit__(self, *exc):
        cache.delete(self.key)


def _notify_staff(req: VolumeRequest):
    """Staff see it in Agency → Approvals (menu badge + in-site toast, polled)."""
    cache.delete("agency:approvals:badge")


# ------------------------------------------------------------------ manager actions
def create_admin(m: GroupManager, data: dict) -> dict:
    from . import admin_crud

    _gate()
    a = assignment_for_group(m, data.get("group_id"))
    rid = _check_role(a, data.get("role_id"))
    gb = _positive_gb(data.get("initial_gb"))
    _check_cap(m, gb)
    username = str(data.get("username") or "").strip()
    if PanelAdmin.objects.filter(username__iexact=username).exists():
        raise ManagerError("an admin with this username already exists", "exists", "username")
    try:
        admin_crud.check_password(data.get("password"), username)    # before anything reaches PasarGuard
    except admin_crud.AdminCrudError as exc:
        raise _from_crud(exc) from exc
    payload = {"username": username, "password": data.get("password"), "role_id": rid,
               "limit_value": str(gb), "limit_unit": "GB", "group_id": a.group_id}
    for k in PROFILE_KEYS:                                            # v1.27: shown on subscription pages
        if data.get(k) not in (None, ""):
            payload[k] = data[k]
    with _AdminLock(username):
        try:
            out = admin_crud.create(_panel(), payload, by=label(m), charge=False, source="manager",
                                    note=f"created by group manager {m.username} — pending approval")
        except admin_crud.AdminCrudError as exc:
            raise _from_crud(exc) from exc
        req = VolumeRequest.objects.create(
            group=a.group, group_name=group_title(a.group), manager=m, manager_username=m.username,
            admin_username=username, kind="create", gb=gb, old_limit_bytes=0, new_limit_bytes=out["limit_bytes"],
            limit_change_id=out.get("history_id"))
    _audit(m, "admin_created", a, admin=username, role_id=rid, gb=str(gb), request=req.id)
    _notify_staff(req)
    return {"username": username, "password": out["password"], "limit_bytes": out["limit_bytes"], "request": req.id,
            "message": f"Admin {username} created with {gb:g} GB — waiting for approval"}


def add_volume(m: GroupManager, username: str, value) -> dict:
    from . import limit_history
    from .actions import gb_label

    _gate()
    gb = _positive_gb(value)
    _check_cap(m, gb)
    with _AdminLock(username):
        a, live = _writable_admin(m, username)
        old = int(live.get("data_limit") or 0)
        if old <= 0:
            raise forbidden("this admin is unlimited — only staff can change it")
        new = old + int(gb * GB)
        try:
            _client()._request("PUT", f"/api/admin/{quote(username, safe='')}", json={"data_limit": new})
        except Exception as exc:  # noqa: BLE001 — PanelError and transport errors alike
            from apps.panel.exceptions import PanelError

            if isinstance(exc, PanelError):
                raise _panel_err(exc) from exc
            raise ManagerError(f"panel error: {exc}", "panel_error") from exc
        with transaction.atomic():
            pa = PanelAdmin.objects.select_for_update().filter(username=username).first()
            if pa is not None:
                pa.admin_limit_bytes, pa.has_data_limit, pa.last_limit_bytes = new, True, new
                pa.admin_remaining = max(0, new - (pa.total_user_used or 0))
                pa.save(update_fields=["admin_limit_bytes", "has_data_limit", "last_limit_bytes", "admin_remaining"])
            req = VolumeRequest.objects.create(
                group=a.group, group_name=group_title(a.group), manager=m, manager_username=m.username,
                admin_username=username, kind="add", gb=gb, old_limit_bytes=old, new_limit_bytes=new)
            h = limit_history.record(username, old, new, action="add", source="manager", by=label(m),
                                     note=f"group manager {m.username}: +{gb:g} GB — pending approval #{req.id}")
            req.limit_change = h
            req.save(update_fields=["limit_change"])
    _audit(m, "volume_added", a, admin=username, gb=str(gb), old_limit_bytes=old, new_limit_bytes=new, request=req.id)
    _notify_staff(req)
    return {"username": username, "old_limit_bytes": old, "new_limit_bytes": new, "request": req.id,
            "message": f"{username}: {gb_label(old)} → {gb_label(new)} — waiting for approval"}


def change_password(m: GroupManager, username: str, password) -> dict:
    from . import admin_crud

    _gate()
    a, _ = _writable_admin(m, username)                 # scope first: a foreign admin is 403, whatever the password
    pw = str(password or "")
    try:
        admin_crud.check_password(pw, username)
    except admin_crud.AdminCrudError as exc:
        raise _from_crud(exc) from exc
    try:
        admin_crud.modify(_panel(), username, {"password": pw})
    except admin_crud.AdminCrudError as exc:
        raise _from_crud(exc) from exc
    _audit(m, "password_changed", a, admin=username)          # never the password
    return {"ok": True, "message": f"Password of {username} changed"}


def change_inbounds(m: GroupManager, username: str, role_id) -> dict:
    from . import admin_crud

    _gate()
    a, live = _writable_admin(m, username)
    rid = _check_role(a, role_id)
    old = (live.get("role") or {}).get("id")
    try:
        out = admin_crud.modify(_panel(), username, {"role_id": rid})
    except admin_crud.AdminCrudError as exc:
        raise _from_crud(exc) from exc
    pa = PanelAdmin.objects.filter(username=username).first()
    if pa is not None:
        raw = dict(pa.raw_data or {})
        raw["role"] = {"id": rid, "name": out["admin"].get("role_name"), "is_owner": False}
        pa.raw_data = raw
        pa.save(update_fields=["raw_data"])
    cat = _safe_catalog()
    _audit(m, "inbounds_changed", a, admin=username, old_role_id=old, new_role_id=rid,
           inbounds=_role_view(rid, cat)["inbounds"])
    return {"ok": True, "role": _role_view(rid, cat), "message": f"Inbounds of {username} changed"}


PROFILE_KEYS = ("support_url", "profile_title")
USER_STATUSES = ("active", "disabled", "limited", "expired", "on_hold")


def admin_profile(m: GroupManager, username: str) -> dict:
    """Live PasarGuard values a manager may see / edit for one of its admins (v1.27)."""
    a, live = _writable_admin(m, username)
    role = live.get("role") or {}
    return {"username": username, "status": "disabled" if live.get("is_disabled") else live.get("status", "active"),
            "support_url": live.get("support_url") or "", "profile_title": live.get("profile_title") or "",
            "role": _role_view(role["id"], _safe_catalog()) if role.get("id") else None}


def update_admin_profile(m: GroupManager, username: str, data: dict) -> dict:
    """Support link + profile title only (v1.27)."""
    from . import admin_crud

    _gate()
    body = {k: data.get(k) or "" for k in PROFILE_KEYS if k in data}
    if not body:
        raise ManagerError("nothing to change", "empty")
    a, live = _writable_admin(m, username)
    try:
        admin_crud.modify(_panel(), username, body)
    except admin_crud.AdminCrudError as exc:
        raise _from_crud(exc) from exc
    _audit(m, "profile_changed", a, admin=username,
           changes={k: [live.get(k) or "", body[k]] for k in body if (live.get(k) or "") != body[k]})
    return {"ok": True, **{k: body[k] for k in body}}


def set_admin_status(m: GroupManager, username: str, enable: bool) -> dict:
    """Enable / disable one admin of the manager's own groups (v1.27). An admin the limit
    enforcement blocked (pamp_blocked) stays with staff: it would just be blocked again."""
    from . import admin_crud

    _gate()
    with _AdminLock(username):
        a, live = _writable_admin(m, username)
        pa = PanelAdmin.objects.filter(username=username).first()
        if enable and pa is not None and pa.pamp_blocked:
            raise forbidden("this admin was blocked for using up its volume — only staff can enable it")
        try:
            admin_crud.modify(_panel(), username, {"status": "active" if enable else "disabled"})
        except admin_crud.AdminCrudError as exc:
            raise _from_crud(exc) from exc
    _audit(m, "admin_enabled" if enable else "admin_disabled", a, admin=username)
    return {"ok": True, "status": "active" if enable else "disabled"}


def admin_users(m: GroupManager, username: str, *, search: str = "", status: str = "", offset=0, limit=20) -> dict:
    """Read-only list of one admin's PasarGuard users (v1.27): own groups only, paged."""
    assignment_for_admin(m, username)
    try:
        offset, limit = max(0, int(offset or 0)), min(100, max(1, int(limit or 20)))
    except (TypeError, ValueError):
        offset, limit = 0, 20
    params = {"admin": [username], "offset": offset, "limit": limit, "sort": "-created_at"}
    if search.strip():
        params["search"] = search.strip()[:64]
    if status:
        if status not in USER_STATUSES:
            raise ManagerError("unknown status", "invalid", "status")
        params["status"] = status
    try:
        data = _client()._request("GET", "/api/users", params=params) or {}
    except Exception as exc:  # noqa: BLE001
        from apps.panel.exceptions import PanelError

        if isinstance(exc, PanelError):
            raise _panel_err(exc) from exc
        raise ManagerError(f"panel error: {exc}", "panel_error") from exc
    rows = []
    for u in data.get("users", []) if isinstance(data, dict) else []:
        owner = (u.get("admin") or {}).get("username") if isinstance(u.get("admin"), dict) else u.get("admin")
        if owner and owner != username:
            continue                                   # never show another admin's user
        rows.append({"username": u.get("username"), "status": u.get("status"), "used_traffic": u.get("used_traffic") or 0,
                     "data_limit": u.get("data_limit") or 0, "expire": u.get("expire"), "online_at": u.get("online_at"),
                     "created_at": u.get("created_at"), "on_hold_expire_duration": u.get("on_hold_expire_duration")})
    total = data.get("total", len(rows)) if isinstance(data, dict) else len(rows)
    return {"admin": username, "results": rows, "total": total, "offset": offset, "limit": limit}


# ------------------------------------------------------------------ staff: approvals
def _day(r: VolumeRequest) -> date:
    return timezone.localdate(r.created_at)


def request_row(r: VolumeRequest) -> dict:
    from . import ledger

    if r.status == "approved" and r.ledger_entry_id:
        e = r.ledger_entry
        price, amount = e.price_per_gb, e.amount
    else:
        q = ledger.quote_quota_charge(r.admin_username, r.old_limit_bytes, r.new_limit_bytes, day=_day(r))
        price, amount = (q["price_per_gb"], q["amount"]) if q else (None, D0)
    return {"id": r.id, "status": r.status, "kind": r.kind, "group_id": r.group_id,
            "group": group_title(r.group) if r.group_id else r.group_name,   # current name (v1.25.3)
            "manager": r.manager_username, "admin": r.admin_username, "gb": r.gb, "date": _day(r),
            "old_limit_bytes": r.old_limit_bytes, "new_limit_bytes": r.new_limit_bytes,
            "price_per_gb": price, "amount": amount, "created_at": r.created_at, "decided_at": r.decided_at,
            "decided_by": r.decided_by, "reason": r.reason, "revert_note": r.revert_note,
            "ledger_entry": r.ledger_entry_id, "limit_change": r.limit_change_id}


def approve(request_id: int, by, *, price=None, may_price: bool = False) -> VolumeRequest:
    from . import ledger

    staff_label = getattr(by, "username", "") or str(by or "")
    with transaction.atomic():
        r = VolumeRequest.objects.select_for_update().filter(pk=request_id).first()
        if r is None:
            raise ManagerError("request not found", "not_found")
        if r.status != "pending":
            raise ManagerError(f"already {r.status}", "not_pending")
        day = _day(r)
        if ledger.price_at(r.admin_username, day) is None:
            if price in (None, ""):
                raise ManagerError(f"{r.admin_username} has no price per GB for {day} — enter one to approve",
                                   "no_price", "price_per_gb")
            if not may_price:
                raise ManagerError("setting a price needs agency.accounting", "forbidden")
            try:
                ledger.set_price(r.admin_username, price, day, note=f"set when approving request #{r.id}", by=staff_label)
            except (ValueError, InvalidOperation) as exc:
                raise ManagerError("enter a valid price per GB", "invalid", "price_per_gb") from exc
        e = ledger.record_quota_charge(r.admin_username, r.old_limit_bytes, r.new_limit_bytes, by=staff_label, day=day,
                                       note=f"approved request #{r.id} — group manager {r.manager_username}")
        r.status, r.decided_at, r.decided_by, r.ledger_entry = "approved", timezone.now(), staff_label[:150], e
        r.save(update_fields=["status", "decided_at", "decided_by", "ledger_entry"])
        if r.limit_change_id:
            AdminLimitChange.objects.filter(pk=r.limit_change_id).update(ledger_entry=e)
    write_audit(action="agency.approval.approved", staff=by, target=r, detail={
        "request": r.id, "group_id": r.group_id, "group": r.group_name, "manager": r.manager_username,
        "admin": r.admin_username, "gb": str(r.gb), "amount": str(e.amount) if e else "0",
        "ledger_entry": e.id if e else None})
    cache.delete("agency:approvals:badge")
    return r


def reject(request_id: int, by, reason: str = "") -> VolumeRequest:
    """Take the volume back on PasarGuard (live limit − GB; never 0 = unlimited), no charge."""
    from . import limit_history
    from .actions import gb_label
    from .admin_crud import AdminCrudError, get_admin

    _gate()
    staff_label = getattr(by, "username", "") or str(by or "")
    r0 = VolumeRequest.objects.filter(pk=request_id).first()
    if r0 is None:
        raise ManagerError("request not found", "not_found")
    with _AdminLock(r0.admin_username), transaction.atomic():
        # the row stays locked across the panel call, so an approval in another tab waits
        r = VolumeRequest.objects.select_for_update().get(pk=r0.pk)
        if r.status != "pending":
            raise ManagerError(f"already {r.status}", "not_pending")
        try:
            live = int(get_admin(_panel(), r.admin_username).get("data_limit") or 0)
        except AdminCrudError as exc:
            raise ManagerError(str(exc), exc.code) from exc
        if live <= 0:
            raise ManagerError("this admin is unlimited now — set its limit first, then reject", "unlimited_now")
        target = max(1, live - int(r.gb * GB))        # 0 would mean unlimited on PasarGuard
        try:
            _client()._request("PUT", f"/api/admin/{quote(r.admin_username, safe='')}", json={"data_limit": target})
        except Exception as exc:  # noqa: BLE001
            from apps.panel.exceptions import PanelError

            if isinstance(exc, PanelError):
                raise _panel_err(exc) from exc
            raise ManagerError(f"panel error: {exc}", "panel_error") from exc
        pa = PanelAdmin.objects.select_for_update().filter(username=r.admin_username).first()
        if pa is not None:
            pa.admin_limit_bytes, pa.has_data_limit, pa.last_limit_bytes = target, True, target
            pa.admin_remaining = max(0, target - (pa.total_user_used or 0))
            pa.save(update_fields=["admin_limit_bytes", "has_data_limit", "last_limit_bytes", "admin_remaining"])
        note = f"rejected request #{r.id} ({r.manager_username}): {gb_label(live)} → {gb_label(target)}"
        limit_history.record(r.admin_username, live, target, action="reduce", source="panel", by=staff_label,
                             note=note[:255])
        r.status, r.decided_at, r.decided_by = "rejected", timezone.now(), staff_label[:150]
        r.reason, r.revert_note = (reason or "").strip()[:255], note[:255]
        r.save(update_fields=["status", "decided_at", "decided_by", "reason", "revert_note"])
    write_audit(action="agency.approval.rejected", staff=by, target=r, detail={
        "request": r.id, "group_id": r.group_id, "group": r.group_name, "manager": r.manager_username,
        "admin": r.admin_username, "gb": str(r.gb), "old_limit_bytes": live, "new_limit_bytes": target,
        "reason": r.reason})
    cache.delete("agency:approvals:badge")
    return r


def badge() -> int:
    n = cache.get("agency:approvals:badge")
    if n is None:
        n = VolumeRequest.objects.filter(status="pending").count()
        cache.set("agency:approvals:badge", n, 30)
    return n


# ------------------------------------------------------------------ accounting (read-only)
def _pending_rows(names, frm=None, to=None) -> list[dict]:
    qs = VolumeRequest.objects.filter(admin_username__in=names, status="pending").order_by("created_at", "id")
    rows = [request_row(r) for r in qs]
    return [r for r in rows if (frm is None or r["date"] >= frm) and (to is None or r["date"] <= to)]


def admin_summaries(names: list[str], frm: date | None = None, to: date | None = None) -> list[dict]:
    """Per admin: charges / payments in the range, balance (all entries up to `to`), pending."""
    out = []
    pend = {}
    for p in _pending_rows(names):
        x = pend.setdefault(p["admin"], {"gb": D0, "amount": D0, "count": 0})
        x["gb"] += p["gb"]; x["amount"] += p["amount"] or D0; x["count"] += 1
    admins = {a.username: a for a in PanelAdmin.objects.filter(username__in=names)}
    for n in names:
        qs = LedgerEntry.objects.filter(admin_username=n, voided=False)
        if to:
            qs = qs.filter(date__lte=to)
        charges = payments = balance = D0
        for e in qs:
            balance += e.signed_amount
            if frm and e.date < frm:
                continue
            if e.kind == LedgerEntry.KIND_PAYMENT:
                payments += e.amount
            else:
                charges += e.amount
        a = admins.get(n)
        out.append({"username": n, "charges": charges, "payments": payments, "balance": balance,
                    "pending": pend.get(n, {"gb": D0, "amount": D0, "count": 0}),
                    "on_panel": a is not None})
    return out


def group_statement(g: AdminGroup, frm: date | None = None, to: date | None = None) -> dict:
    """One combined statement for the group: every charge / payment / adjustment of all its
    admins (admin per row, running balance), plus the pending (unapproved) items apart."""
    names = g.get_all_usernames()
    entries = LedgerEntry.objects.filter(admin_username__in=names).order_by("date", "id")
    if to:
        entries = entries.filter(date__lte=to)
    entries = list(entries)
    opening = sum((e.signed_amount for e in entries if frm and e.date < frm and not e.voided), D0)
    running, rows = opening, []
    charges = payments = D0
    for e in entries:
        if frm and e.date < frm:
            continue
        if not e.voided:
            running += e.signed_amount
            if e.kind == LedgerEntry.KIND_PAYMENT:
                payments += e.amount
            else:
                charges += e.amount
        rows.append({"id": e.id, "date": e.date, "admin": e.admin_username, "kind": e.kind, "gb": e.gb,
                     "price_per_gb": e.price_per_gb, "amount": e.amount, "signed": e.signed_amount, "method": e.method,
                     "note": e.note, "note_fa": _note_fa(e.note), "voided": e.voided, "void_reason": e.void_reason,
                     "balance": running})
    pending = _pending_rows(names)
    all_bal = {}
    for e in LedgerEntry.objects.filter(admin_username__in=names, voided=False):
        all_bal[e.admin_username] = all_bal.get(e.admin_username, D0) + e.signed_amount
    return {
        "group": {"id": g.id, "name": group_title(g), "owner": g.owner_username, "admins": names},
        "from": frm, "to": to, "opening": opening, "charges": charges, "payments": payments, "closing": running,
        "total_debt": sum(all_bal.values(), D0),
        "by_admin": [{"username": n, "balance": all_bal.get(n, D0)} for n in names],
        "entries": rows, "pending": pending,
        "pending_gb": sum((p["gb"] for p in pending), D0),
        "pending_amount": sum((p["amount"] or D0 for p in pending), D0),
    }


def _note_fa(note):
    from .notes import to_fa

    return to_fa(note)


KIND_FA = {"quota_charge": "شارژ حجم", "manual_charge": "بدهکاری", "adjustment": "اصلاحیه", "payment": "پرداخت",
           "pending": "در انتظار تأیید"}
KIND_EN = {"quota_charge": "Quota charge", "manual_charge": "Charge", "adjustment": "Adjustment", "payment": "Payment",
           "pending": "Pending approval"}


def _j(d) -> str:
    from apps.common.jalali import to_jalali_str

    return to_jalali_str(d, "%Y/%m/%d") if d else ""


def group_statement_rows(st: dict, lang: str) -> list[list]:
    fa = lang == "fa"
    k = KIND_FA if fa else KIND_EN
    head = (["تاریخ", "ادمین", "نوع", "گیگ", "قیمت هر گیگ", "مبلغ (تومان)", "اثر", "مانده", "توضیح", "وضعیت"] if fa else
            ["Date", "Admin", "Type", "GB", "Price per GB", "Amount (Toman)", "Signed", "Balance", "Note", "Status"])
    rows = [head]
    if st["from"]:
        rows.append([_j(st["from"]), "", "مانده از قبل" if fa else "Opening balance", "", "", "", "", st["opening"], "", ""])
    for r in st["entries"]:
        rows.append([_j(r["date"]), r["admin"], k.get(r["kind"], r["kind"]), r["gb"] or "", r["price_per_gb"] or "",
                     r["amount"], r["signed"], r["balance"], _note_fa(r["note"]) if fa else r["note"],
                     ("باطل: " if fa else "voided: ") + r["void_reason"] if r["voided"] else ""])
    for p in st["pending"]:
        rows.append([_j(p["date"]), p["admin"], k["pending"], p["gb"], p["price_per_gb"] or "", p["amount"], "", "",
                     f"#{p['id']} · {p['manager']}", "در انتظار" if fa else "pending"])
    rows.append([])
    rows.append(["جمع شارژ" if fa else "Charges", "", "", "", "", st["charges"]])
    rows.append(["جمع پرداخت" if fa else "Payments", "", "", "", "", st["payments"]])
    rows.append(["بدهی کل گروه" if fa else "Group total debt", "", "", "", "", st["total_debt"]])
    rows.append(["در انتظار تأیید" if fa else "Pending (not in the balance)", "", "", st["pending_gb"], "", st["pending_amount"]])
    return rows


def summary_rows(rows: list[dict], lang: str) -> list[list]:
    fa = lang == "fa"
    head = (["ادمین", "شارژ (تومان)", "پرداخت (تومان)", "بدهی (تومان)", "گیگ در انتظار", "مبلغ در انتظار"] if fa else
            ["Admin", "Charges (Toman)", "Payments (Toman)", "Balance (Toman)", "Pending GB", "Pending amount"])
    out = [head] + [[r["username"], r["charges"], r["payments"], r["balance"], r["pending"]["gb"], r["pending"]["amount"]]
                    for r in rows]
    out.append(["جمع" if fa else "Total", sum((r["charges"] for r in rows), D0), sum((r["payments"] for r in rows), D0),
                sum((r["balance"] for r in rows), D0), sum((r["pending"]["gb"] for r in rows), D0),
                sum((r["pending"]["amount"] for r in rows), D0)])
    return out


def statement_rows(st: dict, lang: str) -> list[list]:
    fa = lang == "fa"
    k = KIND_FA if fa else KIND_EN
    head = (["تاریخ", "نوع", "گیگ", "قیمت هر گیگ", "مبلغ (تومان)", "اثر", "مانده", "توضیح", "وضعیت"] if fa else
            ["Date", "Type", "GB", "Price per GB", "Amount (Toman)", "Signed", "Balance", "Note", "Status"])
    rows = [head] + [[_j(r["date"]), k.get(r["kind"], r["kind"]), r["gb"] or "", r["price_per_gb"] or "", r["amount"],
                      r["signed"], r["balance"], _note_fa(r["note"]) if fa else r["note"],
                      ("باطل" if fa else "voided") if r["voided"] else ""]
                     for r in st["entries"]]
    for p in st.get("pending", []):
        rows.append([_j(p["date"]), k["pending"], p["gb"], p["price_per_gb"] or "", p["amount"], "", "", f"#{p['id']}",
                     "در انتظار" if fa else "pending"])
    return rows


def admin_statement(username: str, frm: date | None = None, to: date | None = None) -> dict:
    """ledger.statement for the portal: internal fields removed, range-filtered (the running
    balance still counts everything before the range), pending items apart."""
    from . import ledger

    st = ledger.statement(username)
    for e in st["entries"]:
        e.pop("created_by", None)
    st["prices"] = []
    st["entries"] = [e for e in st["entries"] if (frm is None or e["date"] >= frm) and (to is None or e["date"] <= to)]
    st["pending"] = _pending_rows([username])
    return st


# ------------------------------------------------------------------ activity
def activity(group_ids: list[int], limit: int = 100) -> list[dict]:
    from django.db.models import Q

    q = Q()
    for gid in group_ids:
        q |= Q(detail__group_id=gid)
    if not group_ids:
        return []
    qs = (AuditLog.objects.filter(q).filter(Q(action__startswith="agency.manager.") | Q(action__startswith="agency.approval."))
          .order_by("-created_at", "-id")[:limit])
    titles = {g.id: group_title(g) for g in AdminGroup.objects.filter(pk__in=group_ids)}
    return [{"id": l.id, "at": l.created_at, "action": l.action, "by": l.staff_label,
             "admin": (l.detail or {}).get("admin"),
             "group": titles.get((l.detail or {}).get("group_id")) or (l.detail or {}).get("group"),
             "detail": {k: v for k, v in (l.detail or {}).items() if k not in ("ip",)}} for l in qs]
