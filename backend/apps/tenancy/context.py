"""Which tenant the current code runs for (docs/multi-tenant.md §3, Phase 1 Release B).

- Web requests: `TenantMiddleware` sets it from the Host header (an active `TenantDomain`, or one of our own hosts →
  the default tenant; any other host → 404).
- Processes without a request (Celery, bots, daphne, management commands, tests): the **default tenant** until stores
  exist — later phases pass the tenant explicitly (task argument, device token, bot webhook URL).
- `unscoped()`: platform code that must see every tenant (our staff's cross-store views, ops, backfills). Every use
  is listed in `ALLOWED_UNSCOPED` and checked by a test.

Strict mode (Release C, v1.42.0, `TENANCY_STRICT`, default on): inside the web process (gunicorn, `IN_WEB_PROCESS`)
a tenant-table query with no tenant set raises `NoTenant` — every request gets its tenant from the middleware, so a
query outside one (a thread, code after the response) is a bug and fails closed. Processes without a request (Celery
worker / beat, bots, daphne, manage.py) run in the default tenant by design until later phases pass the tenant along.
`TENANCY_STRICT=false` in .env is the emergency switch back to Release B's lenient mode (default tenant + a warning).
Release B ran 44 h in production with zero "query without a tenant" warnings before strict mode was turned on.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar

from django.conf import settings

log = logging.getLogger("caspintunel")

_current: ContextVar[int | None] = ContextVar("tenant_id", default=None)
_unscoped: ContextVar[bool] = ContextVar("tenant_unscoped", default=False)
_default_id: int | None = None
IN_WEB_PROCESS = False          # set by config/wsgi.py: a missing tenant there is a bug (strict: NoTenant)


class NoTenant(RuntimeError):
    """A tenant table was queried with no tenant set (strict mode)."""


def default_tenant_id() -> int | None:
    global _default_id
    if _default_id is None:
        from .models import Tenant

        _default_id = Tenant.objects.filter(is_default=True).values_list("id", flat=True).first()
    return _default_id


def clear_cache() -> None:
    """Forget the cached default tenant id (tests that re-create tenants)."""
    global _default_id
    _default_id = None


def current_tenant_id() -> int | None:
    """The tenant to scope queries to, or None when unscoped()."""
    if _unscoped.get():
        return None
    tid = _current.get()
    if tid is not None:
        return tid
    if IN_WEB_PROCESS:
        if getattr(settings, "TENANCY_STRICT", True):
            raise NoTenant("no tenant set for this query in a web process (docs/multi-tenant.md §3)")
        log.warning("tenancy: query without a tenant in a web process — default tenant used")
    return default_tenant_id()           # background processes: the default tenant


def is_unscoped() -> bool:
    return _unscoped.get()


def set_tenant(tenant_id: int | None):
    """Set the tenant; returns a token for reset_tenant()."""
    return _current.set(tenant_id)


def reset_tenant(token) -> None:
    _current.reset(token)


@contextmanager
def tenant_context(tenant_id: int):
    token = _current.set(tenant_id)
    try:
        yield
    finally:
        _current.reset(token)


@contextmanager
def unscoped():
    """See every tenant's rows (platform code only — keep the list in ALLOWED_UNSCOPED short)."""
    token = _unscoped.set(True)
    try:
        yield
    finally:
        _unscoped.reset(token)


def tenant_ids() -> list[int]:
    """Every store, ours first (periodic jobs that work on customer data run once per store)."""
    from .models import Tenant

    return list(Tenant.objects.order_by("-is_default", "id").values_list("id", flat=True))


def for_each_tenant(fn, *, name: str = "") -> dict:
    """v1.46 (Phase 4): run `fn()` once per store inside its tenant context. One store failing never stops the others;
    returns {tenant_id: result or {"error": …}}."""
    out = {}
    for tid in tenant_ids():
        try:
            with tenant_context(tid):
                out[tid] = fn()
        except Exception as exc:  # noqa: BLE001
            log.exception("tenancy: %s failed for tenant %s", name or getattr(fn, "__name__", "job"), tid)
            out[tid] = {"error": f"{exc.__class__.__name__}: {exc}"[:300]}
    return out


# files allowed to call unscoped() — tests/test_isolation.py fails on any other use
ALLOWED_UNSCOPED = {
    "apps/tenancy/backfill.py",
    "apps/tenancy/context.py",
}
