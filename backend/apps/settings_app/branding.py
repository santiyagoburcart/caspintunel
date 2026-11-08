"""Per-store branding and settings (multi-tenant Phase 2, v1.43, docs/multi-tenant.md §5 settings_app).

- `branding()`: the current tenant's branding object — `SiteConfig` for the default tenant (caspintunel.com, unchanged)
  and the store's `TenantBranding` row for a reseller store (created on first use with the store's name). Both expose
  the same attributes (site_name_fa / en, logo, favicon, support…, site_domain), so callers never choose.
- `TENANT_KEYS`: the runtime settings a store may set for itself; `utils.get_setting` reads the store's value first
  while that store is the current tenant. v1.47: + the checkout timer / unique-amount range / pending-payment alert.
- `is_store()` / `current_tenant()`: whether the request runs for a reseller store (not the default tenant).
"""
from __future__ import annotations

TENANT_KEYS = frozenset({
    "alert_volume_percent", "alert_expire_days",
    "email_verification_required", "referral_required", "iran_phone_only",
    "force_channel_join", "force_share_phone", "default_language", "product_display_mode",
    # v1.47 (Phase 5): each store's checkout timer and unique-amount range, and its own unconfirmed-payment alert delay
    "unique_amount_reservation_minutes", "unique_amount_min", "unique_amount_max", "pending_payment_alert_minutes",
})


def current_tenant_id() -> int | None:
    from apps.tenancy import context

    try:
        return context.current_tenant_id()
    except Exception:  # noqa: BLE001 — strict mode outside a request: the platform view
        return None


def is_store() -> bool:
    """True while a reseller store (not the default tenant) is the current tenant."""
    from apps.tenancy import context

    tid = current_tenant_id()
    return tid is not None and tid != context.default_tenant_id()


def current_tenant():
    from apps.tenancy.models import Tenant

    tid = current_tenant_id()
    return Tenant.objects.filter(pk=tid).first() if tid else None


def store_branding():
    """The current store's TenantBranding row (created on first use)."""
    from .models import TenantBranding

    row = TenantBranding.objects.first()
    if row is None:
        t = current_tenant()
        row, _ = TenantBranding.objects.get_or_create(defaults={
            "site_name_fa": getattr(t, "name", "") or "", "site_name_en": getattr(t, "name", "") or ""})
    return row


def branding():
    from .models import SiteConfig

    return store_branding() if is_store() else SiteConfig.load()


def store_setting(key: str):
    """(found, typed value) of the current store's own setting for `key` (only TENANT_KEYS)."""
    if key not in TENANT_KEYS or not is_store():
        return False, None
    from .models import TenantSetting

    row = TenantSetting.objects.filter(key=key).first()
    return (True, row.typed) if row is not None else (False, None)


def set_store_setting(key: str, value, value_type: str = "str"):
    from .models import TenantSetting

    if key not in TENANT_KEYS:
        raise ValueError(f"{key} is not a store setting")
    row, _ = TenantSetting.objects.update_or_create(key=key, defaults={"value": str(value), "value_type": value_type})
    return row
