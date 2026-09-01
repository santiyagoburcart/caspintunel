"""
Stateless signed tokens for email verification and password reset.

Uses Django's signing (HMAC on SECRET_KEY). Password-reset tokens also fold in
the current password hash + last_login so a token stops working once the
password changes or is used.
"""
from __future__ import annotations

from django.conf import settings
from django.core import signing

_EMAIL_SALT = "accounts.email-verify"
_RESET_SALT = "accounts.password-reset"


def make_email_verify_token(user) -> str:
    return signing.dumps({"uid": user.pk, "email": user.email}, salt=_EMAIL_SALT)


def read_email_verify_token(token: str) -> dict:
    return signing.loads(token, salt=_EMAIL_SALT, max_age=settings.EMAIL_VERIFY_TOKEN_MAX_AGE)


def _reset_fingerprint(user) -> str:
    stamp = user.last_login.isoformat() if user.last_login else ""
    return f"{user.password}|{stamp}"


def make_password_reset_token(user) -> str:
    return signing.dumps(
        {"uid": user.pk, "fp": _reset_fingerprint(user)}, salt=_RESET_SALT
    )


def read_password_reset_token(token: str, user_model) -> "object":
    data = signing.loads(token, salt=_RESET_SALT, max_age=settings.PASSWORD_RESET_TOKEN_MAX_AGE)
    user = user_model.objects.get(pk=data["uid"])
    if data.get("fp") != _reset_fingerprint(user):
        raise signing.BadSignature("token no longer valid")
    return user
