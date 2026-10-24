"""Throttles that stay fair behind an Iran tunnel (docs/access-mode.md).

Through a tunnel that sends no PROXY protocol every visitor arrives from the
tunnel's own address, so a per-IP limit would throttle (or lock out) everyone at
once. For those requests (settings_app.access.via_tunnel) the "IP" of the
anonymous / scoped limits becomes a per-client key instead — the SPA's random
X-Client-Id, else a hash of the browser's headers — and one generous cap
bounds all tunnel traffic together. Logged-in users are keyed by account as
before. Normal (direct / Cloudflare / PROXY-protocol) requests are unchanged.
"""
from __future__ import annotations

import hashlib
import re

from rest_framework import throttling

_CLIENT_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def tunnel_ident(request) -> str | None:
    from apps.settings_app.access import via_tunnel

    try:
        if not via_tunnel(request):
            return None
    except Exception:  # noqa: BLE001 — never break a request over this
        return None
    cid = (request.META.get("HTTP_X_CLIENT_ID") or "").strip()
    if not _CLIENT_ID.match(cid):
        raw = "|".join(request.META.get(h, "") for h in ("HTTP_USER_AGENT", "HTTP_ACCEPT_LANGUAGE", "HTTP_SEC_CH_UA"))
        cid = "h" + hashlib.sha256(raw.encode()).hexdigest()[:24]
    return f"tunnel:{cid}"


class _TunnelAware:
    def get_ident(self, request):
        return tunnel_ident(request) or super().get_ident(request)


class AnonRateThrottle(_TunnelAware, throttling.AnonRateThrottle):
    pass


class UserRateThrottle(_TunnelAware, throttling.UserRateThrottle):
    pass


class ScopedRateThrottle(_TunnelAware, throttling.ScopedRateThrottle):
    pass


class TunnelAggregateThrottle(throttling.SimpleRateThrottle):
    """All requests that came through the tunnel together (rate "tunnel_total")."""

    scope = "tunnel_total"

    def get_cache_key(self, request, view):
        if tunnel_ident(request) is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": "all"}
