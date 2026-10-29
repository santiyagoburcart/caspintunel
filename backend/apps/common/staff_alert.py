"""Short Telegram alerts to staff: a DM (sales bot) to every active staff member
with a linked Telegram id and the given permission, else the backup chat.
Best effort — never raises; returns how many messages were sent."""
from __future__ import annotations

import logging

log = logging.getLogger("caspintunel")


def alert_staff(text: str, *, perm: str, dedupe_key: str | None = None, ttl: int = 3600) -> int:
    from django.core.cache import cache

    from apps.accounts.models import Staff

    if dedupe_key and not cache.add(dedupe_key, 1, ttl):
        return 0
    sent = 0
    try:
        from apps.telegram.config import sales_client

        client = sales_client()
        if client is not None:
            for staff in Staff.objects.filter(is_active=True, telegram_id__isnull=False):
                if staff.has_perm(perm):
                    try:
                        client.send_message(staff.telegram_id, text, parse_mode=None)
                        sent += 1
                    except Exception as exc:  # noqa: BLE001
                        log.warning("staff alert DM to staff %s failed: %s", staff.pk, exc)
        if not sent:
            from apps.telegram.config import backup_client, get_bot_config
            from apps.telegram.models import BotType

            cfg, bclient = get_bot_config(BotType.BACKUP), backup_client()
            if bclient and cfg and cfg.backup_chat_id:
                bclient.send_message(cfg.backup_chat_id, text, parse_mode=None)
                sent = 1
    except Exception as exc:  # noqa: BLE001
        log.warning("staff alert failed: %s", exc)
    return sent
