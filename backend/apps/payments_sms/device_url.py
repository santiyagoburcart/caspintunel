"""Where an SMS device posts to (v1.48): the address shown for the Android app and the iPhone Shortcut endpoint.

A device belongs to one store (tenant), and a store's requests are recognized by their host, so the address must be
the current store's own domain — our site domain for our store (multi-tenant Phase 5: "SMS devices post to their
store's domain").
"""
from __future__ import annotations


def server_base(request=None) -> str:
    """`https://<domain>` of the current store — `branding.public_base` (one implementation)."""
    from apps.settings_app.branding import public_base

    return public_base(request)
