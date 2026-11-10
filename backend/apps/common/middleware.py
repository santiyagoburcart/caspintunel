"""
Let the operator change the site domain from the panel (`site_config.site_domain`)
without an env edit or rebuild: this middleware keeps `settings.ALLOWED_HOSTS`
(and the CSRF trusted origins) in step with the DB value, cached for 60s.

The env `ALLOWED_HOSTS` stays the baseline; the DB domain is *added*, never
removed, so a bad value in the panel can't lock anyone out of the env hosts.
"""
from __future__ import annotations

import logging
import time

from django.conf import settings
from django.core.cache import cache

log = logging.getLogger("caspintunel")

_CACHE_KEY = "dynamic_allowed_hosts"


class DynamicAllowedHostsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self._base_hosts = list(settings.ALLOWED_HOSTS)
        self._base_csrf = list(getattr(settings, "CSRF_TRUSTED_ORIGINS", []))
        self._seen = None            # the shared token this PROCESS last synced with
        self._synced_at = 0.0

    def __call__(self, request):
        self._sync()
        return self.get_response(request)

    def _sync(self):
        # v1.53.1: `settings.ALLOWED_HOSTS` lives in each worker process, the marker in Redis is shared. Before, the first
        # worker to refresh set the marker and every other worker skipped its own refresh, so a new store domain was
        # refused (DisallowedHost, 400) by some workers until they restarted (pilot rehearsal 2026-11-10). Now the marker
        # is a token: a worker refreshes when the token changed (`cache.delete` by domains / stores → a new token) or
        # when its own copy is older than 60 s.
        token = cache.get(_CACHE_KEY)
        if token is None:
            cache.add(_CACHE_KEY, f"{time.time():.6f}", 60)
            token = cache.get(_CACHE_KEY)
        if token is not None and token == self._seen and time.monotonic() - self._synced_at < 60:
            return
        self._seen, self._synced_at = token, time.monotonic()
        try:
            from apps.settings_app.models import SiteConfig

            domain = (SiteConfig.objects.values_list("site_domain", flat=True).first() or "").strip()
        except Exception:  # noqa: BLE001 - DB not ready / migrations
            domain = ""
        if not domain:
            return

        extra_hosts = {domain, f"www.{domain}"}
        try:                                    # multi-tenant: active store domains (apps/tenancy)
            from apps.tenancy.models import TenantDomain

            for h in TenantDomain.objects.filter(state=TenantDomain.ACTIVE).values_list("host", flat=True):
                extra_hosts |= {h, f"www.{h}"}
        except Exception:  # noqa: BLE001 - DB not ready / migrations
            pass
        settings.ALLOWED_HOSTS = list({*self._base_hosts, *extra_hosts})
        settings.CSRF_TRUSTED_ORIGINS = list({
            *self._base_csrf,
            f"https://{domain}", f"https://www.{domain}",
        })
