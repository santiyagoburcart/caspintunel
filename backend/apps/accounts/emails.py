"""
Graceful email helpers. A mail-server outage must never break registration or
password reset — every send is wrapped and reports success as a bool.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail

from apps.common.models import write_audit

log = logging.getLogger("caspintunel")


def smtp_configured() -> bool:
    """Admin-panel relay, .env SMTP or the local mailserver (apps.common.mail)."""
    from apps.common.mail import mail_configured

    return mail_configured()


def _safe_send(subject: str, body: str, to: str) -> bool:
    if not smtp_configured() or not to:
        return False
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [to],
            fail_silently=False,
        )
        return True
    except Exception as exc:  # noqa: BLE001 - outage tolerance
        log.warning("email send failed to %s: %s", to, exc)
        return False


def send_verification_email(user, token: str) -> bool:
    link = f"{settings.PUBLIC_BASE_URL}/verify-email?token={token}"
    ok = _safe_send(
        subject=f"{settings.PROJECT_NAME} — email verification",
        body=f"Hi {user.name or user.username},\n\nVerify your email:\n{link}\n",
        to=user.email or "",
    )
    return ok


def send_password_reset_email(user, token: str) -> bool:
    link = f"{settings.PUBLIC_BASE_URL}/reset-password?token={token}"
    ok = _safe_send(
        subject=f"{settings.PROJECT_NAME} — password reset",
        body=f"Hi {user.name or user.username},\n\nReset your password:\n{link}\n\n"
        f"If you didn't request this, ignore this email.\n",
        to=user.email or "",
    )
    if not ok:
        write_audit(action="password_reset.email_unavailable", target=user)
    return ok
