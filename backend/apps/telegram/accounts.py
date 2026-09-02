"""Link a Telegram user to a site `User` (architecture: website account == bot account)."""
from __future__ import annotations

import secrets

from django.contrib.auth import get_user_model
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
