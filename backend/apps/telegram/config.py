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


def sales_client() -> TelegramClient | None:
    return client_for(BotType.SALES)


def backup_client() -> TelegramClient | None:
    return client_for(BotType.BACKUP)
