"""Resolve a bot's config + build a client for it (token decrypted by the field)."""
from __future__ import annotations

from django.conf import settings

from .client import TelegramClient
from .models import BotType, TelegramConfig


def get_bot_config(bot_type: str) -> TelegramConfig | None:
    return TelegramConfig.objects.filter(bot_type=bot_type).first()


def _proxy_for(cfg: TelegramConfig | None) -> str | None:
    if cfg and cfg.proxy_url:
        return cfg.proxy_url
    return getattr(settings, "TELEGRAM_PROXY_URL", "") or None


def client_for(bot_type: str) -> TelegramClient | None:
    cfg = get_bot_config(bot_type)
    if not cfg or not cfg.is_active or not cfg.token:
        return None
    return TelegramClient(cfg.token, proxy_url=_proxy_for(cfg))


def our_sales_client() -> TelegramClient | None:
    """OUR sales bot, whatever store the code runs for — staff alerts, our bot's settings (never a customer of a store)."""
    return client_for(BotType.SALES)


def sales_client() -> TelegramClient | None:
    """The bot that talks to the CURRENT store's customers (v1.49, Phase 6): our sales bot for our store, the store's own
    bot (tenancy.TenantBot) in a store context — None when that store has no bot (never our bot for a store's customer)."""
    from apps.tenancy.context import store_id

    tid = store_id()
    if tid is None:
        return client_for(BotType.SALES)
    from apps.tenancy.models import Tenant, TenantBot

    b = TenantBot.objects.filter(tenant_id=tid, tenant__status=Tenant.ACTIVE).first()
    return TelegramClient(b.token, proxy_url=_proxy_for(None)) if b is not None and b.token else None


def backup_client() -> TelegramClient | None:
    return client_for(BotType.BACKUP)
