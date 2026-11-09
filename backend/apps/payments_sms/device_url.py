"""Where an SMS device posts to (v1.48): the Android app, its setup QR and the iPhone Shortcut all use these.

A device belongs to one store (tenant), and a store's requests are recognized by their host, so the address must be
the current store's own domain — our site domain for our store (multi-tenant Phase 5: "SMS devices post to their
store's domain").

Setup QR = `caspin-sms://<host>[:port]?token=<url-encoded token>`. The app (mobile_sms SetupQr.kt) accepts only this
form and turns it into the server URL `https://<host>[:port]`. Change both sides together.
"""
from __future__ import annotations

from urllib.parse import quote, urlsplit

QR_SCHEME = "caspin-sms"


def _host_only(host: str) -> str:
    return (host or "").split(":", 1)[0].strip().lower().rstrip(".")


def server_base(request=None) -> str:
    """`https://<domain>` of the current store (the request's host when it is one of the store's live domains)."""
    from django.conf import settings

    from apps.settings_app.branding import current_tenant_id, is_store

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

    from apps.settings_app.models import SiteConfig

    domain = (SiteConfig.load().site_domain or "").strip().strip("/")
    return f"https://{domain}" if domain else settings.PUBLIC_BASE_URL.rstrip("/")


def setup_uri(base: str, token: str) -> str:
    """The Android setup QR content for a device token on `base` (https://host[:port])."""
    netloc = urlsplit(base).netloc
    return f"{QR_SCHEME}://{netloc}?token={quote(token, safe='')}"
