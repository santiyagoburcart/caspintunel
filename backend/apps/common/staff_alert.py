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
                buttons: list | None = None, silent: bool = False, push: dict | None = None,
                platform: bool = False) -> int:
    """v1.47 (multi-tenant Phase 5): an alert raised while serving a reseller STORE goes only to that store's own staff
    (Staff.tenant = the store; none before Phase 8 — their bot comes in Phase 6), never to our staff or our backup chat.
    `platform=True` = an alert meant for US even when raised in a store context (quota, store domains)."""
    from django.core.cache import cache

    from apps.accounts.models import Staff
    from apps.tenancy.context import store_id

    if dedupe_key and not cache.add(dedupe_key, 1, ttl):
        return 0
    store = None if platform else store_id()
    if store is not None:
        return _alert_store_staff(store, text, perm=perm, buttons=buttons, silent=silent, push=push)
    sent = 0
    markup = {"inline_keyboard": buttons} if buttons else None
    quiet = {"disable_notification": True} if silent else {}     # the client rings by default
    try:
        from apps.telegram.config import our_sales_client

        client = our_sales_client()
        if client is not None:
            for staff in Staff.objects.filter(is_active=True, telegram_id__isnull=False, tenant__isnull=True):
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


def _alert_store_staff(store: int, text: str, *, perm: str, buttons=None, silent=False, push=None) -> int:
    """A store's alert: its own staff only (Staff.tenant) — a DM through the STORE's bot (v1.49) to those with a linked
    Telegram id, and their browsers (Web Push). Never our bot, our staff or our backup chat."""
    sent = 0
    try:
        from apps.accounts.models import Staff
        from apps.telegram.config import sales_client       # in a store context = the store's own bot (or None)

        staff = [s for s in Staff.objects.filter(is_active=True, tenant_id=store) if s.has_perm(perm)]
        client = sales_client() if any(s.telegram_id for s in staff) else None
        if client is not None:
            quiet = {"disable_notification": True} if silent else {}
            extra = {"reply_markup": {"inline_keyboard": buttons}} if buttons else {}
            for s in staff:
                if s.telegram_id:
                    try:
                        client.send_message(s.telegram_id, text, parse_mode=None, **extra, **quiet)
                        sent += 1
                    except Exception as exc:  # noqa: BLE001
                        log.warning("store alert DM to staff %s failed: %s", s.pk, exc)
        if push and staff:
            from apps.notifications.webpush import push_to_staff

            push_to_staff(perm, staff_ids=[s.pk for s in staff], **push)
    except Exception as exc:  # noqa: BLE001
        log.warning("store staff alert failed: %s", exc)
    return sent
