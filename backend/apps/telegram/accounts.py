"""Link a Telegram user to a site `User` (architecture: website account == bot account)."""
from __future__ import annotations

import secrets

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction

from apps.accounts.models import Source
from apps.common.models import write_audit

User = get_user_model()


def _unique_username() -> str:
    for _ in range(20):
        candidate = f"tg_{secrets.token_hex(4)}"
        if not User.objects.filter(username=candidate).exists():
            return candidate
    raise RuntimeError("could not allocate a bot username")


@transaction.atomic
def ensure_bot_user(telegram_id: int, *, telegram_username: str | None = None,
                    phone: str | None = None, name: str | None = None):
    """
    Returns (user, created, generated_password | None).

    First-time bot users get a random username + password for website login
    (architecture §2). Existing users are synced with any newly-known fields.
    """
    user = User.objects.filter(telegram_id=telegram_id).first()
    if user:
        fields = []
        if telegram_username and user.telegram_username != telegram_username:
            user.telegram_username = telegram_username
            fields.append("telegram_username")
        if phone and not user.phone:
            user.phone = phone
            fields.append("phone")
        if name and not user.name:
            user.name = name
            fields.append("name")
        if fields:
            fields.append("updated_at")
            user.save(update_fields=fields)
        return user, False, None

    password = secrets.token_urlsafe(9)
    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=_unique_username(),
                password=password,
                telegram_id=telegram_id,
                telegram_username=telegram_username or "",
                phone=phone or "",
                name=name or "",
                source=Source.BOT,
            )
    except IntegrityError:
        # a concurrent first-contact (two Mini App launches / bot + app at once)
        # already created the row — adopt it instead of failing.
        user = User.objects.filter(telegram_id=telegram_id).first()
        if user is None:
            raise
        return user, False, None
    write_audit(action="user.created_via_bot", target=user, detail={"telegram_id": telegram_id})
    return user, True, password


def link_phone(user, phone: str) -> None:
    """Capture the Telegram phone the first time it is shared."""
    if phone and not user.phone:
        user.phone = phone
        user.save(update_fields=["phone", "updated_at"])


def change_password_via_bot(user, new_password: str) -> None:
    """Set a new password from the sales bot.

    Unlike the website's change-password flow, this does not ask for the
    current password: the user's identity is already proven by chatting
    from their own linked Telegram account (the same trust level the
    website's "forgot password" email link relies on), so it mirrors that
    reset path rather than the in-session change-password one.
    Raises django.core.exceptions.ValidationError if the password is weak.
    """
    validate_password(new_password, user)
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    write_audit(action="password.changed_via_bot", target=user)
