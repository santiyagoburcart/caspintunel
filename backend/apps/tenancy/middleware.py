"""Host → tenant for every web request (docs/multi-tenant.md §3, Phase 1 Release B).

An active `TenantDomain` (exact host, `www.` stripped) → its tenant. Our own hosts (`settings.DOMAIN` + `www`, the panel's
site domain, the env `ALLOWED_HOSTS`, `localhost` / `127.0.0.1` / the test client's host) → the default tenant. Any other
host → 404 — never the default store, so a stranger's domain pointed at our IP shows nothing.
"""
from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
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
    tid = (TenantDomain.objects.filter(host__in={host, bare}, state=TenantDomain.ACTIVE)
           .values_list("tenant_id", flat=True).first())
    if tid is None and host in own_hosts():
        tid = context.default_tenant_id()
    cache.set(key, tid or 0, _TTL)
    return tid


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tid = resolve(request.get_host())
        if tid is None:
            return HttpResponseNotFound("unknown site")
        request.tenant_id = tid
        token = context.set_tenant(tid)
        try:
            return self.get_response(request)
        finally:
            context.reset_tenant(token)
