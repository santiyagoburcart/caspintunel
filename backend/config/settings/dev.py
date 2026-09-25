from .base import *  # noqa: F401,F403
from .base import env

DEBUG = env.bool("DEBUG", default=True)
ALLOWED_HOSTS = ["*"]

# Permissive CORS for local React dev servers.
CORS_ALLOW_ALL_ORIGINS = True

# Mail: DynamicEmailBackend prints to the console when nothing is configured
# and DEBUG is on (apps/common/mail.py).

# Louder logging while developing.
LOGGING["root"]["level"] = "DEBUG"  # noqa: F405
