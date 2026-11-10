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


def _store_prefix() -> str:
    """v1.51 (multi-tenant Phase 7 Release B, docs/multi-tenant.md §13): a store's buckets are its own — `t<id>:` before the
    client key — so one store's visitors never use another store's (or our) budget. Ours: no prefix (keys unchanged)."""
    try:
        from apps.tenancy.context import store_id

        tid = store_id()
    except Exception:  # noqa: BLE001
        return ""
    return f"t{tid}:" if tid else ""


class _TunnelAware:
    def get_ident(self, request):
        return _store_prefix() + (tunnel_ident(request) or super().get_ident(request))


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


class StoreTotalThrottle(throttling.SimpleRateThrottle):
    """A cap on ALL API requests of one store together — `Tenant.limits["requests_per_minute"]`, set by our staff on
    «فروشگاه» (none = no cap). Over it → 429 for that store only + one alert to us an hour."""

    scope = "store_total"

    def get_rate(self):
        return None                        # read per request (allow_request)

    def allow_request(self, request, view):
        try:
            from apps.tenancy.context import store_id
            from apps.tenancy.models import Tenant

            tid = store_id()
            if not tid:
                return True
            limit = int((Tenant.objects.filter(pk=tid).values_list("limits", flat=True).first() or {})
                        .get("requests_per_minute") or 0)
        except Exception:  # noqa: BLE001 — a cap problem never blocks a store
            return True
        if limit <= 0:
            return True
        self.num_requests, self.duration = limit, 60
        self.key = self.cache_format % {"scope": self.scope, "ident": f"t{tid}"}
        self.history = self.cache.get(self.key, [])
        self.now = self.timer()
        while self.history and self.history[-1] <= self.now - self.duration:
            self.history.pop()
        if len(self.history) >= self.num_requests:
            self._alert(tid, limit)
            return self.throttle_failure()
        return self.throttle_success()

    @staticmethod
    def _alert(tid: int, limit: int) -> None:
        try:
            from apps.common.staff_alert import alert_staff
            from apps.tenancy.models import Tenant

            name = Tenant.objects.filter(pk=tid).values_list("name", flat=True).first() or tid
            alert_staff(f"⚠️ فروشگاه «{name}» به سقف درخواست رسید ({limit} در دقیقه) — درخواست‌های اضافه 429 گرفتند.",
                        perm="agency.manage", platform=True, dedupe_key=f"store_cap:{tid}", ttl=3600, silent=True)
        except Exception:  # noqa: BLE001
            pass
