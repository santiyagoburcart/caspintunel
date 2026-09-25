from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

# --- HTTPS / security hardening (Nginx terminates TLS) ---
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=2592000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

if not FIELD_ENCRYPTION_KEY:  # noqa: F405
    raise RuntimeError("FIELD_ENCRYPTION_KEY must be set in production.")
if SECRET_KEY == "dev-insecure-change-me":  # noqa: F405
    raise RuntimeError("SECRET_KEY must be set in production.")

# Receipts: nginx serves the file (via an `internal` location) after Django has
# authorised the request. Override to False if you don't run behind our nginx.
SERVE_MEDIA_VIA_XACCEL = env.bool("SERVE_MEDIA_VIA_XACCEL", default=True)
