"""
Let the operator change the site domain from the panel (`site_config.site_domain`)
without an env edit or rebuild: this middleware keeps `settings.ALLOWED_HOSTS`
(and the CSRF trusted origins) in step with the DB value, cached for 60s.

The env `ALLOWED_HOSTS` stays the baseline; the DB domain is *added*, never
removed, so a bad value in the panel can't lock anyone out of the env hosts.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache

log = logging.getLogger("caspintunel")

_CACHE_KEY = "dynamic_allowed_hosts"


class DynamicAllowedHostsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self._base_hosts = list(settings.ALLOWED_HOSTS)
        self._base_csrf = list(getattr(settings, "CSRF_TRUSTED_ORIGINS", []))

    def __call__(self, request):
        self._sync()
        return self.get_response(request)

    def _sync(self):
        if cache.get(_CACHE_KEY):
            return
        try:
            from apps.settings_app.models import SiteConfig

            domain = (SiteConfig.objects.values_list("site_domain", flat=True).first() or "").strip()
        except Exception:  # noqa: BLE001 - DB not ready / migrations
            domain = ""
        cache.set(_CACHE_KEY, domain or "-", 60)
        if not domain:
            return

        extra_hosts = {domain, f"www.{domain}"}
        settings.ALLOWED_HOSTS = list({*self._base_hosts, *extra_hosts})
        settings.CSRF_TRUSTED_ORIGINS = list({
            *self._base_csrf,
            f"https://{domain}", f"https://www.{domain}",
        })
