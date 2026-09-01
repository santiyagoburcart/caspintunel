"""
Base settings for caspintunel.

Values come from the environment (.env at repo root, loaded by django-environ).
Never hardcode secrets here.
"""
from datetime import timedelta
from pathlib import Path

import environ

# backend/config/settings/base.py -> BASE_DIR = backend/
BASE_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BASE_DIR.parent

env = environ.Env()
# Load .env from repo root if present (compose also injects env_file).
_env_file = REPO_ROOT / ".env"
if _env_file.exists():
    env.read_env(str(_env_file))

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = env("SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

PROJECT_NAME = env("PROJECT_NAME", default="caspintunel")
DOMAIN = env("DOMAIN", default="caspin.skin")

# Encryption key for sensitive model fields (panel password, tokens).
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", default="")

def _read_version() -> str:
    for candidate in (BASE_DIR / "VERSION", REPO_ROOT / "VERSION"):
        if candidate.exists():
            return candidate.read_text().strip()
    return env("VERSION", default="0.0.0")


VERSION = _read_version()

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    "django_celery_beat",
]

LOCAL_APPS = [
    "apps.common",
    "apps.accounts",
    "apps.panel",
    "apps.plans",
    "apps.orders",
    "apps.payments_sms",
    "apps.notifications",
    "apps.telegram",
    "apps.settings_app",
    "apps.ops",
    "apps.adminpanel",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "apps.common.middleware.DynamicAllowedHostsMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database (MySQL)
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env("DB_NAME", default="caspintunel"),
        "USER": env("DB_USER", default="caspintunel"),
        "PASSWORD": env("DB_PASSWORD", default=""),
        "HOST": env("DB_HOST", default="db"),
        "PORT": env("DB_PORT", default="3306"),
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Customer accounts. Panel operators are a separate model: accounts.Staff.
AUTH_USER_MODEL = "accounts.User"

# Cap upload size (receipts are the only user-supplied files).
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# i18n / tz  — store UTC, display Jalali in the presentation layer
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "fa"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

LANGUAGES = [("fa", "فارسی"), ("en", "English")]
LOCALE_PATHS = [BASE_DIR / "locale"]

# ---------------------------------------------------------------------------
# Static / media
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# ---------------------------------------------------------------------------
# DRF / JWT / Swagger
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "600/min",
        "auth": "10/min",        # login / register / password-reset
        "receipt": "20/hour",    # receipt upload
        "sms_ingest": "240/min", # android SMS app
    },
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 20,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MIN", default=30)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}

# Token lifetimes for signed links (email verify / password reset), in seconds.
EMAIL_VERIFY_TOKEN_MAX_AGE = env.int("EMAIL_VERIFY_TOKEN_MAX_AGE", default=60 * 60 * 48)
PASSWORD_RESET_TOKEN_MAX_AGE = env.int("PASSWORD_RESET_TOKEN_MAX_AGE", default=60 * 60 * 2)

# Public base URL used to build links in emails (falls back to the domain).
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL", default=f"https://{DOMAIN}")

SPECTACULAR_SETTINGS = {
    "TITLE": "caspintunel API",
    "DESCRIPTION": "VPN sales system — website, admin panel, Telegram bots, SMS app.",
    "VERSION": VERSION,
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "OrderTypeEnum": "apps.orders.models.OrderType",
        "PlanTypeEnum": "apps.plans.models.PlanType",
        "ServiceStatusEnum": "apps.panel.models.ServiceStatus",
        "OrderStatusEnum": "apps.orders.models.OrderStatus",
        "PaymentStatusEnum": "apps.payments_sms.models.PaymentStatus",
        "PaymentMethodEnum": "apps.payments_sms.models.PaymentMethod",
    },
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=[f"https://{DOMAIN}", f"https://www.{DOMAIN}"],
)

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://redis:6379/1")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://redis:6379/2")
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_TIME_LIMIT = 300
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# ---------------------------------------------------------------------------
# Cache (Redis)
# ---------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://redis:6379/0"),
    }
}

# ---------------------------------------------------------------------------
# Email — graceful during outages (see apps.notifications later)
# ---------------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@caspin.skin")

# ---------------------------------------------------------------------------
# External services (also overridable from panel settings later)
# ---------------------------------------------------------------------------
PANEL_BASE_URL = env("PANEL_BASE_URL", default="")
PANEL_ADMIN_USERNAME = env("PANEL_ADMIN_USERNAME", default="")
PANEL_ADMIN_PASSWORD = env("PANEL_ADMIN_PASSWORD", default="")
PANEL_HTTP_TIMEOUT = env.int("PANEL_HTTP_TIMEOUT", default=15)
PANEL_TOKEN_TTL_SECONDS = env.int("PANEL_TOKEN_TTL_SECONDS", default=60 * 60 * 23)
PANEL_SYNC_ENABLED = env.bool("PANEL_SYNC_ENABLED", default=True)
PANEL_SYNC_INTERVAL_MINUTES = env.int("PANEL_SYNC_INTERVAL_MINUTES", default=15)

# ---------------------------------------------------------------------------
# Monitoring
# ---------------------------------------------------------------------------
HEALTHCHECK_SITE_URL = env("HEALTHCHECK_SITE_URL", default="http://web:8000/api/v1/health/")
RESOURCE_DISK_PATH = env("RESOURCE_DISK_PATH", default="/")
BOT_HEARTBEAT_TTL = env.int("BOT_HEARTBEAT_TTL", default=180)  # seconds
BACKUP_RETENTION_DAYS = env.int("BACKUP_RETENTION_DAYS", default=14)

# ---------------------------------------------------------------------------
# Self-update (panel "update" button)
# ---------------------------------------------------------------------------
# raw VERSION file of the deployed branch; blank = update check disabled
UPDATE_CHECK_URL = env(
    "UPDATE_CHECK_URL",
    default="https://raw.githubusercontent.com/santiyagoburcart/caspintunel/main/VERSION",
)
# a host-side watcher (scripts/watch-update.sh) runs update.sh when this file appears
UPDATE_SENTINEL_PATH = env("UPDATE_SENTINEL_PATH", default="/app/backups/.update-requested")

CLOUDFLARE_API_TOKEN = env("CLOUDFLARE_API_TOKEN", default="")
CLOUDFLARE_ZONE = env("CLOUDFLARE_ZONE", default="caspin.skin")

TELEGRAM_PROXY_URL = env("TELEGRAM_PROXY_URL", default="")

# ---------------------------------------------------------------------------
# Logging — never crash on an outage; log and move on
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{levelname} {asctime} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        "caspintunel": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
