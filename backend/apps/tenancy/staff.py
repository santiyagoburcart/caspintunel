"""A reseller store's own staff (v1.52, multi-tenant Phase 8 — docs/multi-tenant.md §11).

* Store staff = `Staff.tenant = <store>`; store roles = `Role.tenant = <store>`. They sign in and their tokens work ONLY on
  that store's domains (`adminpanel.tokens.staff_for_payload`, `StaffLoginView`); never on ours or another store's.
* Ceiling: `Tenant.permission_ceiling` = the codes a store may hold and grant — set by OUR staff on «فروشگاه», always ⊆
  `STORE_CODES` (the codes the store-safe panel views ask for; everything else is platform-only, a test keeps the list honest).
  `Staff.has_perm` never grants a store staff more than the ceiling; lowering it also strips the codes from the store's roles
  at once (audit). Store staff are never Super Admin.
* The store owner = one store staff on the store's «مالک فروشگاه» role, which always equals the ceiling; our staff create it
  (and reset its password — shown once, never stored or audited) on «فروشگاه». The owner manages the store's other roles
  (codes ⊆ ceiling ∩ the owner's own) and staff in the store panel.
"""
from __future__ import annotations

import secrets

from django.db import transaction

# every code a store-safe (store_ok) admin view asks for, + managing the store's own staff / roles
STORE_CODES = frozenset({
    "users.view", "users.manage", "users.delete",
    "plans.manage",
    "payment.view", "payment.approve", "sms.manage",
    "settings.manage", "pages.manage", "themes.manage",
    "tickets.view", "tickets.reply", "tickets.assign", "tickets.close", "tickets.manage_topics",
    "discounts.view", "discounts.manage",
    "monitoring.view",                  # the store dashboard's service counts only (server health is ours)
    "roles.manage",                     # the store's own staff and roles
})
DEFAULT_CEILING = sorted(STORE_CODES)
OWNER_ROLE = "store-owner"              # Role.name of the store's owner role (per store; name_fa below)
OWNER_ROLE_FA = "مالک فروشگاه"


class StaffError(Exception):
    def __init__(self, en: str, fa: str, status: int = 400, field: str = ""):
        super().__init__(en)
        self.en, self.fa, self.status, self.field = en, fa, status, field


def ceiling(tenant_id: int | None) -> frozenset:
    """The store's codes (empty for an unknown store); our staff (None) have no ceiling here."""
    from .models import Tenant

    if not tenant_id:
        return frozenset()
    codes = Tenant.objects.filter(pk=tenant_id).values_list("permission_ceiling", flat=True).first() or []
    return frozenset(codes) & STORE_CODES


def owner_role(t, *, create: bool = True):
    from apps.accounts.models import Role

    role = Role.objects.filter(tenant=t, name=OWNER_ROLE).first()
    if role is None and create:
        role = Role.objects.create(tenant=t, name=OWNER_ROLE, name_fa=OWNER_ROLE_FA,
                                   description="The reseller — everything the store may do",
                                   description_fa="نماینده — هر کاری که فروشگاه اجازه دارد")
    return role


@transaction.atomic
def set_ceiling(t, codes, *, staff=None) -> list[str]:
    """Our staff only. Codes outside STORE_CODES are refused; the store's roles lose anything above the new ceiling."""
    from apps.accounts.models import Permission, Role
    from apps.common.models import write_audit

    want = {str(c) for c in (codes or [])}
    bad = sorted(want - STORE_CODES)
    if bad:
        raise StaffError(f"platform-only permissions cannot be given to a store: {', '.join(bad)}",
                         f"این دسترسی‌ها فقط برای پنل ما هستند و به فروشگاه داده نمی‌شوند: {', '.join(bad)}", field="codes")
    before = sorted(t.permission_ceiling or [])
    t.permission_ceiling = sorted(want)
    t.save(update_fields=["permission_ceiling", "updated_at"])
    stripped = {}
    for role in Role.objects.filter(tenant=t).exclude(name=OWNER_ROLE).prefetch_related("permissions"):
        extra = [p for p in role.permissions.all() if p.code not in want]
        if extra:
            role.permissions.remove(*extra)
            stripped[role.name] = sorted(p.code for p in extra)
    owner = owner_role(t, create=False)
    if owner is not None:
        owner.permissions.set(Permission.objects.filter(code__in=want))
    write_audit(action="store.ceiling", staff=staff, target=t,
                detail={"tenant": t.pk, "before": before, "after": t.permission_ceiling, "stripped": stripped})
    return t.permission_ceiling


@transaction.atomic
def ensure_owner(t, username: str = "", *, staff=None) -> tuple:
    """(owner staff, new password) — creates the store's owner on the first call (username required), resets its password
    afterwards. The password is returned ONCE (shown to our staff to pass on), never stored in clear or audited."""
    from apps.accounts.models import Permission, Staff
    from apps.common.models import write_audit

    role = owner_role(t)
    role.permissions.set(Permission.objects.filter(code__in=ceiling(t.pk)))
    owner = Staff.objects.filter(tenant=t, role=role).order_by("id").first()
    password = secrets.token_urlsafe(12)
    if owner is None:
        name = (username or "").strip()
        if not name or len(name) < 3 or len(name) > 64:
            raise StaffError("the owner's username is required (3–64 characters)", "نام کاربری مالک فروشگاه را وارد کنید (۳ تا ۶۴ نویسه)",
                             field="username")
        if Staff.objects.filter(username__iexact=name).exists():
            raise StaffError("that username is taken", "این نام کاربری قبلاً گرفته شده است", status=409, field="username")
        owner = Staff(tenant=t, username=name, role=role, is_active=True, is_superadmin=False)
        owner.set_password(password)
        owner.save()
        write_audit(action="store.owner_created", staff=staff, target=t, detail={"tenant": t.pk, "owner": owner.username})
    else:
        owner.set_password(password)                   # also bumps token_version: every old session of the owner ends
        owner.is_active = True
        owner.save(update_fields=["password_hash", "token_version", "is_active", "updated_at"])
        write_audit(action="store.owner_password_reset", staff=staff, target=t, detail={"tenant": t.pk, "owner": owner.username})
    return owner, password


def owner_row(t) -> dict | None:
    from apps.accounts.models import Staff

    role = owner_role(t, create=False)
    owner = Staff.objects.filter(tenant=t, role=role).order_by("id").first() if role else None
    if owner is None:
        return None
    return {"username": owner.username, "is_active": owner.is_active, "last_login": owner.last_login,
            "staff_count": Staff.objects.filter(tenant=t).count()}


# ------------------------------------------------------------------ checks used by the store panel
def grantable(actor) -> frozenset:
    """Codes `actor` may put into a store role in the CURRENT store: ⊆ the ceiling, and ⊆ the actor's own codes for a store
    staff (our staff working on a store's panel: the whole ceiling)."""
    from .context import store_id

    tid = store_id()
    cap = ceiling(tid)
    if getattr(actor, "tenant_id", None):
        own = frozenset(actor.role.permissions.values_list("code", flat=True)) if actor.role_id else frozenset()
        return cap & own
    return cap


def check_role_codes(actor, codes) -> None:
    allowed = grantable(actor)
    bad = sorted({str(c) for c in codes} - allowed)
    if bad:
        raise StaffError(f"outside what this store may grant: {', '.join(bad)}",
                         f"این دسترسی‌ها خارج از سقف این فروشگاه یا دسترسی خودتان است: {', '.join(bad)}", status=403,
                         field="permission_codes")
