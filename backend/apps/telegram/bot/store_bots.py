"""Store bots (v1.49, multi-tenant Phase 6): one TeleBot object per store and process, with the SAME handlers as our
sales bot (`sales_bot._register`), fed one webhook update at a time (`process`, run by the Celery task
`apps.telegram.tasks.store_bot_update_task` inside the store's tenant context). No polling, no thread.

Inside a store bot everything resolves to that store: customers (User is tenant-scoped), plans, orders, branding texts,
`sales_client()` (its token), the Mini App URL (its domain), the per-user step state (key includes the tenant). Staff
flows (staff link, `st:*`, `ag:*`) are off — our staff never work through a reseller's bot (store staff: Phase 8).
"""
from __future__ import annotations

import logging
import threading

log = logging.getLogger("caspintunel")

_lock = threading.Lock()
_bots: dict[int, tuple[str, object]] = {}      # tenant id → (token, TeleBot)


def forget(tenant_id: int) -> None:
    with _lock:
        _bots.pop(tenant_id, None)


def bot_for(tenant_id: int):
    """The store's TeleBot (handlers registered), or None without an active store bot."""
    import telebot

    from apps.tenancy.models import Tenant, TenantBot

    b = TenantBot.objects.filter(tenant_id=tenant_id, tenant__status=Tenant.ACTIVE).first()
    if b is None or not b.token:
        forget(tenant_id)
        return None
    with _lock:
        hit = _bots.get(tenant_id)
        if hit and hit[0] == b.token:
            return hit[1]
    from .sales_bot import _register

    bot = telebot.TeleBot(b.token, parse_mode="HTML", threaded=False)
    _register(bot)
    with _lock:
        _bots[tenant_id] = (b.token, bot)
    return bot


def username(tenant_id: int) -> str:
    from apps.tenancy.models import TenantBot

    return TenantBot.objects.filter(tenant_id=tenant_id).values_list("username", flat=True).first() or ""


def process(tenant_id: int, update: dict) -> bool:
    """Run one Telegram update through the store's handlers (caller sets the tenant context). False = no bot."""
    from telebot import types

    bot = bot_for(tenant_id)
    if bot is None:
        return False
    upd = types.Update.de_json(update)
    try:
        bot.process_new_updates([upd])
    except Exception as exc:  # noqa: BLE001 — one bad update must never block the store's next ones
        log.exception("store bot %s: update %s failed: %s", tenant_id, update.get("update_id"), exc)
    return True
