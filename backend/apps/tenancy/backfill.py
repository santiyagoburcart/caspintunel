"""Default tenant + backfill (Phase 1 Release A). Idempotent: used by the migrations, by tests and safe to re-run.
Only rows whose `tenant` is still NULL are touched (UPDATE … WHERE tenant_id IS NULL)."""
from __future__ import annotations

from . import registry

DEFAULT_SLUG = "default"


def ensure_default(apps=None, *, domain: str | None = None):
    """The default tenant (our own store) and its verified domain. Returns the tenant."""
    from django.apps import apps as live_apps
    from django.conf import settings

    apps = apps or live_apps
    Tenant = apps.get_model("tenancy", "Tenant")
    TenantDomain = apps.get_model("tenancy", "TenantDomain")
    t = Tenant.objects.filter(is_default=True).first()
    sc = None
    try:
        sc = apps.get_model("settings_app", "SiteConfig").objects.first()
    except LookupError:
        pass
    if t is None:
        name = ((getattr(sc, "site_name_en", "") or getattr(sc, "site_name_fa", "")) if sc else "") or "Caspian Tunnel"
        t = Tenant.objects.create(slug=DEFAULT_SLUG, name=name[:150], status="active", is_default=True)
    host = (domain or (getattr(sc, "site_domain", "") if sc else "") or getattr(settings, "DOMAIN", "") or "")
    host = host.strip().lower().rstrip(".")
    if host and not TenantDomain.objects.filter(host=host).exists():
        mode = "direct"
        try:
            dc = apps.get_model("settings_app", "DomainConfig").objects.first()
            mode = {"tunnel": "tunnel", "cloudflare": "cloudflare"}.get(getattr(dc, "access_mode", ""), "direct")
        except LookupError:
            pass
        TenantDomain.objects.create(tenant=t, host=host, role="both", mode=mode, state="active")
    return t


def backfill(apps=None) -> dict[str, int]:
    """Set the default tenant on every TENANT row (and NULLABLE rows matching BACKFILL_FILTER) that has none."""
    from django.apps import apps as live_apps

    from .context import unscoped

    apps = apps or live_apps
    t = ensure_default(apps)
    done = {}
    for label in registry.TENANT + [m for m in registry.NULLABLE if m in registry.BACKFILL_FILTER]:
        model = apps.get_model(*label.split("."))
        with unscoped():                    # the live (scoped) models: see the rows that have no tenant yet
            qs = model.objects.filter(tenant__isnull=True, **registry.BACKFILL_FILTER.get(label, {}))
            done[label] = qs.update(tenant_id=t.pk)
    return done
