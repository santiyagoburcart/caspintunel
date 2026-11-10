"""Absolute links into the admin panel for Telegram messages (the admin path can be moved —
settings_app/paths.py — so it is read at send time)."""
from django.conf import settings


def admin_link(route: str = "/") -> str:
    try:
        from apps.settings_app.paths import state

        base = state()["admin"] or "/panel"
    except Exception:  # noqa: BLE001
        base = "/panel"
    # v1.50: the CURRENT store's address (a store's alert links to its own panel; ours to ours)
    from apps.settings_app.branding import public_base

    site = public_base() or settings.PUBLIC_BASE_URL
    return f"{site.rstrip('/')}/{base.strip('/')}/{route.lstrip('/')}"
