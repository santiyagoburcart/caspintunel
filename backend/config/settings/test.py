"""Settings for the test suite: no throttling, local-memory cache, dummy email."""
from .base import *  # noqa: F401,F403
from .base import REST_FRAMEWORK

DEBUG = False
ALLOWED_HOSTS = ["*"]
CORS_ALLOW_ALL_ORIGINS = True

# Disable DRF throttling so rapid successive test requests don't hit 429.
# Views that pin their own throttle_classes (public reads) still need a rate
# per scope, so keep every scope but make it unreachable.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {k: "100000/min" for k in REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]},
}

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
# no Redis at all in tests: WebSocket pushes stay in-process (tests used to
# group_send into the LIVE channel layer), Celery runs eagerly (below)
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
# deterministic regardless of the operator's .env; tests that need a configured
# host set settings.EMAIL_HOST themselves.
EMAIL_HOST = ""

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # faster tests

# Run Celery tasks inline.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

PANEL_TOKEN_TTL_SECONDS = 3600


# ---------------------------------------------------------------------------
# SAFETY GUARD — the suite must never touch the live database or Redis.
# Tests run only in the isolated stack (docker-compose.test.yml via
# scripts/test.sh): DB host `test-db`, Redis host `test-redis`. Anything else
# stops Django before a single connection is opened. The production names (and
# whatever addresses they resolve to) are refused even if allow-listed.
# ---------------------------------------------------------------------------
def _refuse_production_services():
    import os
    import socket
    from urllib.parse import urlparse

    from django.core.exceptions import ImproperlyConfigured

    prod_names = {"db", "redis", "mysql", "caspintunel-db-1", "caspintunel-redis-1"}
    allowed_db = {"test-db"} | set(filter(None, os.environ.get("TEST_ALLOWED_DB_HOSTS", "").split(",")))
    allowed_redis = {"test-redis"} | set(filter(None, os.environ.get("TEST_ALLOWED_REDIS_HOSTS", "").split(",")))

    def resolve(host):
        try:
            return {ai[4][0] for ai in socket.getaddrinfo(host, None)}
        except (OSError, UnicodeError):
            return set()

    prod_ips = set().union(*(resolve(h) for h in prod_names))
    problems = []

    db_host = (DATABASES["default"].get("HOST") or "").strip()  # noqa: F405
    if db_host not in allowed_db:
        problems.append(f"DB host {db_host!r} is not an isolated test DB (allowed: {sorted(allowed_db)})")
    if db_host in prod_names or (resolve(db_host) & prod_ips):
        problems.append(f"DB host {db_host!r} is the PRODUCTION database")

    for var in ("REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND", "CHANNELS_REDIS_URL"):
        host = urlparse(os.environ.get(var, "")).hostname
        if not host:
            continue
        if host not in allowed_redis:
            problems.append(f"{var} host {host!r} is not an isolated test Redis (allowed: {sorted(allowed_redis)})")
        if host in prod_names or (resolve(host) & prod_ips):
            problems.append(f"{var} points at the PRODUCTION Redis ({host!r})")

    if problems:
        raise ImproperlyConfigured(
            "Refusing to run tests against live services:\n  - " + "\n  - ".join(problems)
            + "\nRun the suite with ./scripts/test.sh (isolated test DB + Redis)."
        )


_refuse_production_services()
