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
    # v1.51 (Phase 7 Release B): each store's own ticket rules (tickets/rules.py SETTINGS + BOOL_SETTINGS)
    "tickets_max_open_per_user", "tickets_auto_close_days", "tickets_reopen_days", "tickets_show_staff_name",
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


def _host_only(host: str) -> str:
    return (host or "").split(":", 1)[0].strip().lower().rstrip(".")


def public_base(request=None) -> str:
    """`https://<domain>` customers of the CURRENT store use (v1.48, v1.49 moved here): a store's live domain (the request's
    host when it is one of them, else its first site domain), our `SiteConfig.site_domain` / PUBLIC_BASE_URL otherwise.
    Used by the SMS apps' address, the iPhone Shortcut endpoint and a store bot's Mini App / links."""
    from django.conf import settings

    if is_store():
        from apps.tenancy.models import TenantDomain

        hosts = list(TenantDomain.objects.filter(tenant_id=current_tenant_id(), state=TenantDomain.ACTIVE)
                     .order_by("id").values_list("host", "role"))
        if request is not None:
            asked = _host_only(request.get_host())
            if any(h == asked for h, _ in hosts):
                return f"https://{asked}"
        site = [h for h, role in hosts if role != TenantDomain.ADMIN] or [h for h, _ in hosts]
        if site:
            return f"https://{site[0]}"
        if request is not None:          # a store without a live domain yet: the host it is using now
            return f"https://{_host_only(request.get_host())}"
        return ""                        # no address yet (a store bot shows no Mini App button)

    from .models import SiteConfig

    domain = (SiteConfig.load().site_domain or "").strip().strip("/")
    return f"https://{domain}" if domain else settings.PUBLIC_BASE_URL.rstrip("/")


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
