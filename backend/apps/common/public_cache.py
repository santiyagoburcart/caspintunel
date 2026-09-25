"""Short server-side cache for the public read endpoints (/config/, /theme/,
/pages/, /plans/). Every page load of both SPAs hits them, so they are served
from Redis for PUBLIC_CACHE_TTL seconds instead of rebuilding from MySQL.

Invalidation: any save/delete of the models behind them bumps one version
number (settings_app.signals), so admin edits show up at once. The TTL only
bounds staleness for writes that bypass signals (queryset.update).

A cache outage never breaks the endpoint — it just falls through to the DB.
"""
from __future__ import annotations

import logging
from typing import Callable

from django.core.cache import cache
from rest_framework.response import Response

log = logging.getLogger("caspintunel")

PUBLIC_CACHE_TTL = 60
_VERSION_KEY = "public-cache:version"


def _version() -> int:
    v = cache.get(_VERSION_KEY)
    if v is None:
        cache.add(_VERSION_KEY, 1, None)
        v = cache.get(_VERSION_KEY) or 1
    return v


def bump_public_cache() -> None:
    """Invalidate every cached public response."""
    try:
        cache.incr(_VERSION_KEY)
    except ValueError:  # key missing
        cache.set(_VERSION_KEY, 2, None)
    except Exception as exc:  # noqa: BLE001 - never break a save
        log.warning("public cache bump failed: %s", exc)


def cached_public(request, name: str, build: Callable[[], Response]) -> Response:
    """Return `build()`'s Response, cached per host + full path for 60s.
    Only 200 responses are cached."""
    try:
        key = f"public:{_version()}:{name}:{request.get_host()}:{request.get_full_path()}"
        hit = cache.get(key)
    except Exception as exc:  # noqa: BLE001
        log.warning("public cache read failed: %s", exc)
        return build()
    if hit is not None:
        return Response(hit)
    resp = build()
    if resp.status_code == 200:
        try:
            cache.set(key, resp.data, PUBLIC_CACHE_TTL)
        except Exception as exc:  # noqa: BLE001
            log.warning("public cache write failed: %s", exc)
    return resp
