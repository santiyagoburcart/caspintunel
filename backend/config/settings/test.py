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

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
# deterministic regardless of the operator's .env; tests that need a configured
# host set settings.EMAIL_HOST themselves.
EMAIL_HOST = ""

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # faster tests

# Run Celery tasks inline.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

PANEL_TOKEN_TTL_SECONDS = 3600
