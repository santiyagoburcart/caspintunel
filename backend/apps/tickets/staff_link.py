"""Link a staff account to their Telegram (ticket DMs from the sales bot).

The panel asks for a one-time code (10 minutes, single use, kept in the cache —
only its hash); the staff member opens `t.me/<bot>?start=staff-<CODE>` (or
sends `/start staff-<CODE>`) and the sales bot calls `redeem`. The code is
the proof that the Telegram account belongs to the logged-in staff member.
"""
from __future__ import annotations

import hashlib
import secrets

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone

PREFIX = "staff-"
TTL = 600
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _key(code: str) -> str:
    return "tickets:stafflink:" + hashlib.sha256(code.strip().upper().encode()).hexdigest()


def new_code(staff) -> str:
    code = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    cache.set(_key(code), staff.id, TTL)
    return code


def deep_link(code: str) -> str | None:
    """v1.52: our staff link with OUR bot; a store's staff with THAT store's bot (the current store)."""
    try:
        from apps.tenancy.context import store_id

        tid = store_id()
        if tid:
            from apps.telegram.bot.store_bots import username

            name = username(tid) or None
            return f"https://t.me/{name}?start={PREFIX}{code}" if name else None
        from apps.telegram.config import our_sales_client

        client = our_sales_client()
        name = client.get_me().get("username") if client else None
    except Exception:  # noqa: BLE001 — the code also works typed after /start
        name = None
    return f"https://t.me/{name}?start={PREFIX}{code}" if name else None


def redeem(code: str, telegram_id: int) -> str:
    """'linked' | 'invalid' | 'taken' (Telegram already linked to another staff)."""
    from apps.accounts.models import Staff

    key = _key(code)
    staff_id = cache.get(key)
    if not staff_id:
        return "invalid"
    cache.delete(key)
    staff = Staff.objects.filter(pk=staff_id, is_active=True).first()
    from apps.tenancy.context import store_id

    if staff is None or staff.tenant_id != store_id():
        return "invalid"            # v1.52: a code is redeemed only in its own store's bot (ours: our bot)
    if Staff.objects.filter(telegram_id=telegram_id).exclude(pk=staff.pk).exists():
        return "taken"
    try:
        with transaction.atomic():
            staff.telegram_id = telegram_id
            staff.telegram_linked_at = timezone.now()
            staff.save(update_fields=["telegram_id", "telegram_linked_at"])
    except IntegrityError:
        return "taken"
    from apps.common.models import write_audit

    write_audit(action="staff.telegram_linked", staff=staff, target=staff)
    return "linked"


CONFIRM_PREFIX = "sl:"


def link_by_id(staff, telegram_id: int) -> str:
    """v1.60.1 «آیدی عددی تلگرام»: the bot (the store's own on a store, ours on ours) DMs that id a one-time «تأیید اتصال»
    button — tapping it (from that account) is the proof, exactly like the deep link. 'sent' | 'not_started' | 'no_bot' |
    'taken'. The account must have opened the bot (/start) once, else Telegram refuses the message."""
    from apps.accounts.models import Staff

    if Staff.objects.filter(telegram_id=telegram_id).exclude(pk=staff.pk).exists():
        return "taken"
    from apps.tenancy.context import store_id

    if store_id():
        from apps.telegram.config import sales_client

        client = sales_client()
    else:
        from apps.telegram.config import our_sales_client

        client = our_sales_client()
    if client is None:
        return "no_bot"
    code = new_code(staff)
    try:
        client.send_message(telegram_id, f"🔐 اتصال این حساب تلگرام به پنل به‌عنوان «{staff.username}»؟\n"
                                         f"Link this Telegram account to the panel as “{staff.username}”?", parse_mode=None,
                            reply_markup={"inline_keyboard": [[{"text": "✅ تأیید اتصال · Confirm",
                                                                "callback_data": f"{CONFIRM_PREFIX}{code}"}]]})
    except Exception:  # noqa: BLE001 — Telegram: "chat not found" / "bot was blocked" = never opened the bot
        cache.delete(_key(code))
        return "not_started"
    return "sent"
