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


SETUP_PREFIX = "SMS1:"


def setup_code(base: str, token: str) -> str:
    """v1.60 «کد راه‌اندازی» for the Android app: `SMS1:` + base64url(JSON {"u": address, "t": token}) without padding.
    The app (SettingsActivity.applySetupCode) decodes it; the manual fields stay as the fallback. Contains the device token,
    so it is shown only to staff with sms.manage, like the token itself."""
    import base64
    import json

    raw = json.dumps({"u": base.rstrip("/"), "t": token}, separators=(",", ":")).encode()
    return SETUP_PREFIX + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def parse_setup_code(code: str) -> dict:
    """The inverse (tests + docs): {"u": …, "t": …}; ValueError when it is not a setup code."""
    import base64
    import json

    code = (code or "").strip()
    if not code.startswith(SETUP_PREFIX):
        raise ValueError("not a setup code")
    body = code[len(SETUP_PREFIX):]
    data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    if not isinstance(data, dict) or not data.get("u") or not data.get("t"):
        raise ValueError("incomplete setup code")
    return data
