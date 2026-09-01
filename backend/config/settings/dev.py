from .base import *  # noqa: F401,F403
from .base import env

DEBUG = env.bool("DEBUG", default=True)
ALLOWED_HOSTS = ["*"]

# Permissive CORS for local React dev servers.
CORS_ALLOW_ALL_ORIGINS = True

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Louder logging while developing.
LOGGING["root"]["level"] = "DEBUG"  # noqa: F405
