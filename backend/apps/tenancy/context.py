"""Which tenant the current code runs for (docs/multi-tenant.md §3, Phase 1 Release B).

- Web requests: `TenantMiddleware` sets it from the Host header (an active `TenantDomain`, or one of our own hosts →
  the default tenant; any other host → 404).
- Processes without a request (Celery, bots, daphne, management commands, tests): the **default tenant** until stores
  exist — later phases pass the tenant explicitly (task argument, device token, bot webhook URL).
- `unscoped()`: platform code that must see every tenant (our staff's cross-store views, ops, backfills). Every use
  is listed in `ALLOWED_UNSCOPED` and checked by a test.

Release B is lenient: a query on a tenant table with no tenant set falls back to the default tenant and, inside a web
request process, logs a warning. Release C turns `TENANCY_STRICT` on (fail closed) once the logs show no warning.
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
IN_WEB_PROCESS = False          # set by config/wsgi.py: a missing tenant there is a bug worth a warning


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
    if getattr(settings, "TENANCY_STRICT", False):
        raise NoTenant("no tenant set for this query (docs/multi-tenant.md §3)")
    if IN_WEB_PROCESS:
        log.warning("tenancy: query without a tenant in a web process — default tenant used")
    return default_tenant_id()


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


# files allowed to call unscoped() — tests/test_isolation.py fails on any other use
ALLOWED_UNSCOPED = {
    "apps/tenancy/backfill.py",
    "apps/tenancy/context.py",
}
