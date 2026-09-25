"""Business logic for accounts: email verification, password reset, legacy import."""
from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.common.models import write_audit
from apps.settings_app.utils import get_setting

from . import emails, tokens
from .managers import generate_referral_code

log = logging.getLogger("caspintunel")
User = get_user_model()


# --- email verification (flowchart 1.1) ------------------------------------
def dispatch_verification(user) -> str:
    """
    Returns one of: 'skipped' (feature off), 'sent', 'not_sent' (SMTP outage),
    'no_email' (user has no address). Never raises.
    """
    if not get_setting("email_verification_required", False):
        return "skipped"
    if not user.email:
        return "no_email"
    token = tokens.make_email_verify_token(user)
    ok = emails.send_verification_email(user, token)
    return "sent" if ok else "not_sent"


def confirm_email(token: str) -> User:
    data = tokens.read_email_verify_token(token)
    user = User.objects.get(pk=data["uid"])
    if not user.email_verified:
        user.email_verified = True
        user.save(update_fields=["email_verified", "updated_at"])
        write_audit(action="email.verified", target=user)
    return user


# --- password reset (flowchart 1.6) --------------------------------------
def resolve_user(identifier: str) -> User | None:
    return (
        User.objects.filter(username__iexact=identifier).first()
        or User.objects.filter(email__iexact=identifier).first()
    )


def start_password_reset(identifier: str) -> dict:
    """
    Email path. Always returns a generic result (no user enumeration).
    `email_sent` tells the caller whether the link actually went out; if not,
    the response should point the user at the bot / admin paths.
    """
    user = resolve_user(identifier)
    result = {"email_sent": False, "alternative_paths": ["telegram_bot", "contact_admin"]}
    if not user or not user.is_active:
        return result
    if user.email and emails.smtp_configured():
        token = tokens.make_password_reset_token(user)
        result["email_sent"] = emails.send_password_reset_email(user, token)
    return result


def confirm_password_reset(token: str, new_password: str) -> User:
    user = tokens.read_password_reset_token(token, User)
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    write_audit(action="password.reset_completed", target=user)
    return user


def set_password_by_admin(user, new_password: str, staff=None) -> None:
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    write_audit(action="password.set_by_admin", target=user, staff=staff)


def set_password_via_bot(telegram_id: int, new_password: str) -> User | None:
    """Used by the sales bot's reset flow (phase 9) after it verifies identity."""
    user = User.objects.filter(telegram_id=telegram_id, is_active=True).first()
    if not user:
        return None
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    write_audit(action="password.reset_via_bot", target=user)
    return user


# --- legacy import -------------------------------------------------------
@transaction.atomic
def import_legacy_users(rows: list[dict], overwrite: bool = False, staff=None) -> dict:
    created, updated, skipped = 0, 0, 0
    for row in rows:
        username = row["username"]
        existing = User.objects.filter(username__iexact=username).first()
        if existing and not overwrite:
            skipped += 1
            continue

        target = existing or User(username=username)
        target.email = row.get("email") or target.email or None
        target.name = row.get("name", "") or target.name
        if row.get("phone"):
            from .phone import normalize_ir_phone, normalize_phone

            target.phone = normalize_ir_phone(row["phone"]) or normalize_phone(row["phone"]) or target.phone
        if row.get("telegram_id"):
            target.telegram_id = row["telegram_id"]
        target.is_legacy = True
        target.is_active = True
        if not target.referral_code:
            target.referral_code = _unique_code()

        pw = row.get("password")
        if pw:
            target.set_password(pw)
        elif not existing:
            # No known password → account exists but must use a reset path to log in.
            target.set_unusable_password()

        target.save()
        created += 0 if existing else 1
        updated += 1 if existing else 0

    write_audit(
        action="users.legacy_import",
        staff=staff,
        detail={"created": created, "updated": updated, "skipped": skipped},
    )
    return {"created": created, "updated": updated, "skipped": skipped}


def _unique_code() -> str:
    for _ in range(20):
        code = generate_referral_code()
        if not User.objects.filter(referral_code=code).exists():
            return code
    raise RuntimeError("could not allocate referral_code")
