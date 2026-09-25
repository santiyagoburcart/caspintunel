"""Outgoing mail: one Django email backend for every app email.

Which SMTP server is used is decided at SEND time, in this order:

  1. "db"    — relay set in the admin panel (EmailSettings, enabled + host)
  2. "env"   — EMAIL_HOST/PORT/USER/PASSWORD/USE_TLS from .env, when it is an
               external server
  3. "local" — the local `mailserver` container (EMAIL_HOST=mailserver), which
               only delivers if the host allows outbound port 25 (or has its
               own SMTP_RELAY_* set)
  (none)     — nothing configured: messages are dropped (console in DEBUG)

The admin-panel settings are cached per process for a few seconds; a save
bumps a version number in the cache so every process (gunicorn workers,
celery, bots) reloads on its next send. The password is never put in the
cache — only the version number is.
"""
from __future__ import annotations

import logging
import smtplib
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from email.utils import formataddr

from django.conf import settings
from django.core.cache import cache
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.smtp import EmailBackend as SMTPBackend
from django.utils import timezone

log = logging.getLogger("caspintunel")

LOCAL_HOSTS = {"mailserver", "mail", "localhost", "127.0.0.1"}
_VERSION_KEY = "email-settings:version"
_LOCAL_TTL = 30  # seconds a process trusts its copy without checking the version

_lock = threading.Lock()
_cached: dict = {"row": None, "version": None, "at": 0.0}


@dataclass(frozen=True)
class MailConfig:
    source: str            # "db" | "env" | "local" | "none"
    host: str = ""
    port: int = 0
    use_tls: bool = False  # STARTTLS
    use_ssl: bool = False  # implicit TLS (465)
    username: str = ""
    password: str = ""
    from_email: str = ""   # full From header ("Name <addr>") or ""

    @property
    def configured(self) -> bool:
        return self.source != "none"


# ---------------------------------------------------------------- settings row
def bump_email_settings_version() -> None:
    try:
        cache.incr(_VERSION_KEY)
    except ValueError:
        cache.set(_VERSION_KEY, 2, None)
    except Exception as exc:  # noqa: BLE001 - never break a save
        log.warning("email settings cache bump failed: %s", exc)
    with _lock:
        _cached.update(row=None, version=None, at=0.0)


def _version():
    try:
        return cache.get(_VERSION_KEY)
    except Exception:  # noqa: BLE001 - cache down: fall back to the TTL
        return None


def _settings_row():
    """The EmailSettings row, from a short per-process cache."""
    from apps.settings_app.models import EmailSettings

    now = time.monotonic()
    with _lock:
        row, ver, at = _cached["row"], _cached["version"], _cached["at"]
    if row is not None and now - at < _LOCAL_TTL and _version() == ver:
        return row
    try:
        row = EmailSettings.objects.filter(pk=1).first()
    except Exception as exc:  # noqa: BLE001 - DB hiccup: use the .env path
        log.warning("email settings unavailable: %s", exc)
        return None
    with _lock:
        _cached.update(row=row, version=_version(), at=now)
    return row


def resolve_mail_config() -> MailConfig:
    row = _settings_row()
    if row is not None and row.enabled and row.host:
        sender = ""
        if row.from_email:
            sender = formataddr((row.from_name, row.from_email)) if row.from_name else row.from_email
        return MailConfig(
            source="db", host=row.host, port=int(row.port or 587),
            use_tls=row.security == "starttls", use_ssl=row.security == "ssl",
            username=row.username or "", password=row.password or "", from_email=sender,
        )
    host = (getattr(settings, "EMAIL_HOST", "") or "").strip()
    if host:
        return MailConfig(
            source="local" if host in LOCAL_HOSTS else "env",
            host=host, port=int(settings.EMAIL_PORT),
            use_tls=bool(settings.EMAIL_USE_TLS), use_ssl=bool(getattr(settings, "EMAIL_USE_SSL", False)),
            username=settings.EMAIL_HOST_USER or "", password=settings.EMAIL_HOST_PASSWORD or "",
        )
    return MailConfig(source="none")


def mail_configured() -> bool:
    return resolve_mail_config().configured


# ---------------------------------------------------------------- errors
def describe_smtp_error(exc: BaseException) -> dict:
    """Map an SMTP/socket exception to a short code + readable fa/en text."""
    raw = str(exc) or exc.__class__.__name__
    low = raw.lower()
    # servers that need a login often reject MAIL FROM (smtplib then raises
    # SMTPSenderRefused) — the reply text says what's really wrong
    auth_required = isinstance(exc, smtplib.SMTPResponseException) and not isinstance(
        exc, smtplib.SMTPAuthenticationError) and any(
        k in low for k in ("authenticate first", "authentication required", "auth required", "must authenticate",
                           "not authenticated", "relay access denied", "5.7.0 authentication"))
    if auth_required:
        code, fa, en = ("auth_required", "سرور ورود (نام کاربری و رمز SMTP) می‌خواهد — نام کاربری و رمز را وارد و ذخیره کنید.",
                        "The server requires login — enter the SMTP username and password and save.")
    elif isinstance(exc, smtplib.SMTPAuthenticationError):
        code, fa, en = ("auth_failed", "احراز هویت ناموفق — نام کاربری یا رمز SMTP را سرویس‌دهنده رد کرد.",
                        "Authentication failed — the provider rejected the SMTP username or password.")
    elif isinstance(exc, smtplib.SMTPSenderRefused):
        code, fa, en = ("sender_refused", "آدرس فرستنده رد شد — دامنه/آدرس فرستنده باید نزد سرویس‌دهنده تأیید شده باشد.",
                        "Sender refused — the From address/domain must be verified at the provider.")
    elif isinstance(exc, smtplib.SMTPRecipientsRefused):
        code, fa, en = ("recipient_refused", "آدرس گیرنده رد شد.", "The recipient address was refused.")
    elif isinstance(exc, smtplib.SMTPNotSupportedError) or "STARTTLS extension not supported" in raw:
        code, fa, en = ("tls_unsupported", "سرور از STARTTLS پشتیبانی نمی‌کند — نوع امنیت یا پورت را بررسی کنید.",
                        "The server doesn't support STARTTLS — check the security mode / port.")
    elif isinstance(exc, ssl.SSLError):
        code, fa, en = ("tls_error", "خطای TLS/SSL — نوع امنیت با پورت هم‌خوان نیست (587 = STARTTLS، 465 = SSL).",
                        "TLS/SSL error — security mode doesn't match the port (587 = STARTTLS, 465 = SSL).")
    elif isinstance(exc, (socket.timeout, TimeoutError)):
        code, fa, en = ("timeout", "مهلت اتصال تمام شد — میزبان/پورت در دسترس نیست (پورت 25 روی این سرور بسته است؛ از 587 استفاده کنید).",
                        "Connection timed out — host/port unreachable (port 25 is blocked on this server; use 587).")
    elif isinstance(exc, socket.gaierror):
        code, fa, en = ("host_not_found", "نام میزبان SMTP پیدا نشد.", "SMTP host name not found.")
    elif isinstance(exc, ConnectionRefusedError):
        code, fa, en = ("connection_refused", "اتصال رد شد — روی این پورت سرویس SMTP فعال نیست.",
                        "Connection refused — nothing is listening on that port.")
    elif isinstance(exc, smtplib.SMTPServerDisconnected):
        code, fa, en = ("disconnected", "سرور اتصال را قطع کرد — معمولاً نوع امنیت/پورت اشتباه است.",
                        "The server closed the connection — usually a wrong security mode/port.")
    elif isinstance(exc, smtplib.SMTPException):
        code, fa, en = ("smtp_error", "سرور SMTP خطا برگرداند.", "The SMTP server returned an error.")
    elif isinstance(exc, OSError):
        code, fa, en = ("network_error", "خطای شبکه هنگام اتصال به SMTP.", "Network error while connecting to SMTP.")
    else:
        code, fa, en = ("error", "ارسال ناموفق بود.", "Sending failed.")
    return {"code": code, "fa": fa, "en": en, "raw": raw[:500]}


# ---------------------------------------------------------------- status
def _record(success: bool, source: str, error: str = "") -> None:
    from apps.settings_app.models import EmailSettings

    now = timezone.now()
    try:
        EmailSettings.load()  # make sure the row exists
        if success:
            EmailSettings.objects.filter(pk=1).update(last_success_at=now, last_source=source)
        else:
            EmailSettings.objects.filter(pk=1).update(last_error=error[:1000], last_error_at=now, last_source=source)
    except Exception as exc:  # noqa: BLE001 - status is best effort
        log.warning("could not record email status: %s", exc)


# ---------------------------------------------------------------- backend
class DynamicEmailBackend(BaseEmailBackend):
    """settings.EMAIL_BACKEND for the whole app (see module docstring)."""

    def __init__(self, fail_silently=False, timeout=None, **kwargs):
        super().__init__(fail_silently=fail_silently)
        self.timeout = timeout or getattr(settings, "EMAIL_TIMEOUT", 10)

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        cfg = resolve_mail_config()
        if not cfg.configured:
            if settings.DEBUG:
                from django.core.mail.backends.console import EmailBackend as Console

                return Console().send_messages(email_messages)
            _record(False, "none", "no SMTP configured (admin panel relay off, EMAIL_HOST empty)")
            if not self.fail_silently:
                raise smtplib.SMTPException("no SMTP server configured")
            return 0
        if cfg.from_email:
            for m in email_messages:
                # only replace the app default; an explicit sender stays as is
                if not m.from_email or m.from_email == settings.DEFAULT_FROM_EMAIL:
                    m.from_email = cfg.from_email
        smtp = SMTPBackend(
            host=cfg.host, port=cfg.port, username=cfg.username or None, password=cfg.password or None,
            use_tls=cfg.use_tls, use_ssl=cfg.use_ssl, timeout=self.timeout, fail_silently=False,
        )
        try:
            sent = smtp.send_messages(email_messages)
        except Exception as exc:  # noqa: BLE001
            d = describe_smtp_error(exc)
            _record(False, cfg.source, f"[{d['code']}] {d['raw']}")
            log.warning("email via %s (%s:%s) failed: %s", cfg.source, cfg.host, cfg.port, d["raw"])
            if not self.fail_silently:
                raise
            return 0
        _record(True, cfg.source)
        return sent


def probe_connection(cfg: MailConfig | None = None, timeout: int = 10) -> tuple[bool, str]:
    """Connect (+ STARTTLS/SSL + login when credentials are set) to the SMTP
    server that would be used right now, without sending anything."""
    cfg = cfg or resolve_mail_config()
    if not cfg.configured:
        return False, "SMTP not configured"
    smtp = SMTPBackend(
        host=cfg.host, port=cfg.port, username=cfg.username or None, password=cfg.password or None,
        use_tls=cfg.use_tls, use_ssl=cfg.use_ssl, timeout=timeout, fail_silently=False,
    )
    try:
        smtp.open()
        smtp.close()
    except Exception as exc:  # noqa: BLE001
        d = describe_smtp_error(exc)
        return False, f"{cfg.source} {cfg.host}:{cfg.port} — {d['en']} ({d['raw'][:120]})"
    return True, f"SMTP reachable ({cfg.source}: {cfg.host}:{cfg.port})"
