"""Host → tenant for every web request (docs/multi-tenant.md §3, Phase 1 Release B).

An active `TenantDomain` (exact host, `www.` stripped) → its tenant. Our own hosts (`settings.DOMAIN` + `www`, the panel's
site domain, the env `ALLOWED_HOSTS`, `localhost` / `127.0.0.1` / the test client's host) → the default tenant. Any other
host → 404 — never the default store, so a stranger's domain pointed at our IP shows nothing.
"""
from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.http import HttpResponseNotFound

from . import context

_CACHE = "tenancy:host:{}"
_TTL = 60
_BUILTIN_HOSTS = {"localhost", "127.0.0.1", "testserver"}


def own_hosts() -> set[str]:
    hosts = set(_BUILTIN_HOSTS)
    for h in [getattr(settings, "DOMAIN", "")] + list(getattr(settings, "TENANCY_BASE_HOSTS", []) or []):
        h = (h or "").strip().lower().rstrip(".")
        if h and h != "*":
            hosts |= {h, f"www.{h}"}
    try:
        from apps.settings_app.models import SiteConfig

        d = (SiteConfig.objects.values_list("site_domain", flat=True).first() or "").strip().lower()
        if d:
            hosts |= {d, f"www.{d}"}
    except Exception:  # noqa: BLE001 — DB not ready
        pass
    return hosts


def resolve(host: str) -> int | None:
    """The tenant id for this host, or None (unknown host). Cached 60 s."""
    host = (host or "").split(":")[0].strip().lower().rstrip(".")
    key = _CACHE.format(host)
    hit = cache.get(key)
    if hit is not None:
        return hit or None
    from .models import TenantDomain

    bare = host[4:] if host.startswith("www.") else host
    # v1.43: only an ACTIVE store answers on its domains (draft / suspended / closed → unknown site, 404)
    tid = (TenantDomain.objects.filter(host__in={host, bare}, state=TenantDomain.ACTIVE)
           .filter(Q(tenant__status="active") | Q(tenant__is_default=True))
           .values_list("tenant_id", flat=True).first())
    if tid is None and host in own_hosts():
        tid = context.default_tenant_id()
    cache.set(key, tid or 0, _TTL)
    return tid


# v1.43 (Phase 2): platform endpoints that never answer on a reseller store's domain — they do not use the admin
# store-mode guard (StaffPermission.store_ok): Django admin, the agency portal / group-manager API, Blu, the SMS devices
# (per store in Phase 5), staff-only customer-API approve / reject, the API schema.
STORE_BLOCKED_PREFIXES = ("/admin/", "/api/v1/agency/", "/api/v1/payments/blu/", "/api/v1/payments/sms/",
                          "/api/schema", "/api/docs", "/api/redoc")
_STAFF_PAYMENT_ACTIONS = ("/approve/", "/reject/")


def blocked_on_store(path: str) -> bool:
    if path.startswith(STORE_BLOCKED_PREFIXES):
        return True
    return path.startswith("/api/v1/payments/") and path.endswith(_STAFF_PAYMENT_ACTIONS)


def forget_hosts(tenant_id: int) -> None:
    """Drop the cached host → store answers of this store's domains (after a status / domain change)."""
    from .models import TenantDomain

    for h in TenantDomain.objects.filter(tenant_id=tenant_id).values_list("host", flat=True):
        cache.delete_many([_CACHE.format(h), _CACHE.format(f"www.{h}")])


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tid = resolve(request.get_host())
        if tid is None:
            return HttpResponseNotFound("unknown site")
        if tid != context.default_tenant_id() and blocked_on_store(request.path):
            return HttpResponseNotFound("not available on this site")
        request.tenant_id = tid
        token = context.set_tenant(tid)
        try:
            return self.get_response(request)
        finally:
            context.reset_tenant(token)
