"""Short Telegram alerts to staff: a DM (sales bot) to every active staff member
with a linked Telegram id and the given permission, else the backup chat.
Best effort — never raises; returns how many Telegram messages were sent.

v1.33: messages ring (disable_notification=false) unless `silent` (low priority:
"back online", "resolved"); optional inline `buttons` (DMs only — the backup chat is
another bot, it could not answer them); and a browser push (Web Push) to the same
staff when `push` is given ({title, body, url, tag})."""
from __future__ import annotations

import logging

log = logging.getLogger("caspintunel")


def alert_staff(text: str, *, perm: str, dedupe_key: str | None = None, ttl: int = 3600,
                buttons: list | None = None, silent: bool = False, push: dict | None = None) -> int:
    from django.core.cache import cache

    from apps.accounts.models import Staff

    if dedupe_key and not cache.add(dedupe_key, 1, ttl):
        return 0
    sent = 0
    markup = {"inline_keyboard": buttons} if buttons else None
    quiet = {"disable_notification": True} if silent else {}     # the client rings by default
    try:
        from apps.telegram.config import sales_client

        client = sales_client()
        if client is not None:
            for staff in Staff.objects.filter(is_active=True, telegram_id__isnull=False):
                if staff.has_perm(perm):
                    try:
                        extra = {"reply_markup": markup} if markup else {}
                        client.send_message(staff.telegram_id, text, parse_mode=None, **extra, **quiet)
                        sent += 1
                    except Exception as exc:  # noqa: BLE001
                        log.warning("staff alert DM to staff %s failed: %s", staff.pk, exc)
        if not sent:
            from apps.telegram.config import backup_client, get_bot_config
            from apps.telegram.models import BotType

            cfg, bclient = get_bot_config(BotType.BACKUP), backup_client()
            if bclient and cfg and cfg.backup_chat_id:
                bclient.send_message(cfg.backup_chat_id, text, parse_mode=None, **quiet)
                sent = 1
    except Exception as exc:  # noqa: BLE001
        log.warning("staff alert failed: %s", exc)
    if push:
        try:
            from apps.notifications.webpush import push_to_staff

            push_to_staff(perm, **push)
        except Exception as exc:  # noqa: BLE001
            log.warning("staff web push failed: %s", exc)
    return sent
