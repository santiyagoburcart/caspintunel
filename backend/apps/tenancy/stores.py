"""Our staff open a reseller store (multi-tenant Phase 2, D5: only we enable stores and set them up).

Agency → admin page → «فروشگاه»: `enable(username)` creates the store (draft) for that PasarGuard admin with its own
branding row and a copy of our pages (rules, help…) as a starting point; `update` changes name / status / export
permission. Domains (Phase 3) and the bot token (Phase 6) are added to this section later; until a domain is active the
store is not reachable at all. Every change is audit-logged.
"""
from __future__ import annotations

from django.db import transaction
from django.utils.text import slugify

from apps.common.models import write_audit

from . import context
from .models import Tenant, TenantDomain

STATUSES = {Tenant.DRAFT, Tenant.ACTIVE, Tenant.SUSPENDED, Tenant.CLOSED}


class StoreError(Exception):
    def __init__(self, en: str, fa: str, status: int = 400):
        super().__init__(en)
        self.en, self.fa, self.status = en, fa, status


def store_of(username: str) -> Tenant | None:
    return Tenant.objects.filter(reseller_username__iexact=username, is_default=False).first()


def row(t: Tenant | None, *, staff_view: bool = True) -> dict | None:
    if t is None:
        return None
    from apps.settings_app.models import TenantBranding

    from . import bots, domains
    from . import staff as staff_mod

    with context.tenant_context(t.pk):
        b = TenantBranding.objects.first()
    return {
        "id": t.id, "slug": t.slug, "name": t.name, "status": t.status, "reseller": t.reseller_username,
        "export_allowed": t.export_allowed, "limits": t.limits, "created_at": t.created_at,
        "domains": domains.rows_for(t.pk, staff=staff_view),      # v1.45 (Phase 3): records, checks, certificate, health
        "bot": bots.row(t, staff_view=staff_view),                 # v1.49 (Phase 6): username + webhook state, never the token
        # v1.52 (Phase 8): the store owner's login (never its password) and the permission ceiling we set
        "owner": staff_mod.owner_row(t) if staff_view else None,
        "ceiling": sorted(t.permission_ceiling or []),
        "store_codes": sorted(staff_mod.STORE_CODES) if staff_view else None,
        # v1.52.1: paid orders PasarGuard refused («ساخت ناموفق») — listed + retried on «فروشگاه» too
        "failed_orders": _failed_count(t) if staff_view else None,
        # v1.53: the monthly fee hook (off by default) — our staff only
        "fee": _fee_row(t) if staff_view else None,
        "branding": {"site_name_fa": b.site_name_fa, "site_name_en": b.site_name_en} if b else None,
        "reachable": t.status == Tenant.ACTIVE and TenantDomain.objects.filter(tenant=t, state=TenantDomain.ACTIVE).exists(),
    }


def _fee_row(t: Tenant) -> dict:
    from . import fees

    return fees.row(t)


def _failed_count(t: Tenant) -> int:
    from . import failed_orders

    with context.tenant_context(t.pk):
        return failed_orders.count()


def _slug(username: str) -> str:
    base = (slugify(username) or "store")[:40]
    slug, n = base, 2
    while Tenant.objects.filter(slug=slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


@transaction.atomic
def enable(username: str, *, name: str = "", staff=None) -> Tenant:
    from apps.agency.models import PanelAdmin
    from apps.settings_app.models import Page, TenantBranding
    from apps.tickets.defaults import starter_topics
    from apps.tickets.models import TicketTopic

    if not PanelAdmin.objects.filter(username__iexact=username).exists():
        raise StoreError(f"admin {username} not found", f"ادمین {username} پیدا نشد", 404)
    if store_of(username) is not None:
        raise StoreError("this admin already has a store", "این ادمین قبلاً فروشگاه دارد", 409)
    name = (name or username).strip()[:150]
    from .staff import DEFAULT_CEILING

    t = Tenant.objects.create(slug=_slug(username), name=name, reseller_username=username, status=Tenant.DRAFT,
                              permission_ceiling=list(DEFAULT_CEILING))     # v1.52: the default template (we can lower it)
    with context.tenant_context(context.default_tenant_id()):
        pages = list(Page.objects.values("slug", "title_fa", "title_en", "body_fa", "body_en", "is_active"))
        topics = starter_topics()                    # v1.52.1: customers can open tickets from day one
    with context.tenant_context(t.pk):
        TenantBranding.objects.create(site_name_fa=name, site_name_en=name)
        for p in pages:                              # our pages as a starting point; the store edits its own copies
            Page.objects.create(**p)
        for tp in topics:                            # our ticket topics as a starting point (no staff scopes)
            TicketTopic.objects.create(**tp)
    write_audit(action="store.enabled", staff=staff, target=t,
                detail={"reseller": username, "slug": t.slug, "name": name, "pages_copied": len(pages),
                        "topics_copied": len(topics)})
    return t


@transaction.atomic
def update(t: Tenant, data: dict, *, staff=None) -> Tenant:
    t = Tenant.objects.select_for_update().get(pk=t.pk)
    if t.is_default:
        raise StoreError("the default store is not managed here", "فروشگاه اصلی از اینجا مدیریت نمی‌شود", 403)
    before = {"name": t.name, "status": t.status, "export_allowed": t.export_allowed,
              "requests_per_minute": (t.limits or {}).get("requests_per_minute")}
    if "name" in data:
        n = str(data.get("name") or "").strip()[:150]
        if not n:
            raise StoreError("the store name is required", "نام فروشگاه را وارد کنید")
        t.name = n
    if "status" in data:
        st = str(data.get("status") or "")
        if st not in STATUSES:
            raise StoreError(f"status must be one of {sorted(STATUSES)}", "وضعیت نامعتبر است")
        t.status = st
    if "export_allowed" in data:
        t.export_allowed = str(data.get("export_allowed")).lower() in ("1", "true", "yes", "on") or data.get("export_allowed") is True
    if "requests_per_minute" in data:                    # v1.51: cap on all of the store's API requests (0 / empty = none)
        raw = data.get("requests_per_minute")
        try:
            rpm = int(raw or 0)
        except (TypeError, ValueError):
            raise StoreError("requests_per_minute must be a number", "سقف درخواست باید عدد باشد") from None
        if rpm and not 60 <= rpm <= 100000:
            raise StoreError("requests_per_minute must be 0 (no cap) or 60–100000", "سقف درخواست: ۰ (بدون سقف) یا 60 تا 100000")
        t.limits = {**(t.limits or {}), "requests_per_minute": rpm or None}
    t.save()
    if t.export_allowed != before["export_allowed"]:        # v1.53: the switch also puts store.export in / out of the ceiling
        from .staff import set_ceiling

        codes = set(t.permission_ceiling or [])
        set_ceiling(t, (codes | {"store.export"}) if t.export_allowed else (codes - {"store.export"}), staff=staff)
    after = {"name": t.name, "status": t.status, "export_allowed": t.export_allowed,
             "requests_per_minute": (t.limits or {}).get("requests_per_minute")}
    if after != before:
        write_audit(action="store.updated", staff=staff, target=t, detail={"before": before, "after": after})
        from .middleware import forget_hosts

        forget_hosts(t.pk)                                  # host → store answers are cached 60 s
        transaction.on_commit(lambda: forget_hosts(t.pk))   # … and once more after commit (a request in between)
    return t
