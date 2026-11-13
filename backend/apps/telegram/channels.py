"""Mandatory channels (forced join) — one status check shared by the panel's «بررسی» and the periodic sync.

v1.60.1 stores: a store manages its own channels on its panel («ربات تلگرام», settings.manage). A store channel is enforced
only while its bot is an ADMIN there (else the bot cannot read membership and would lock every customer out), and a store
needs no separate switch: active channels where the bot is admin = enforced, none = off. Our own bot keeps its rules.
"""
from __future__ import annotations

import logging

from django.utils import timezone

log = logging.getLogger("caspintunel")


def refresh(channel, client) -> dict:
    """getChat + getChatMemberCount + getChatMember(bot): stores title / count / bot_is_admin. Returns the status row."""
    from .client import TelegramError

    out = {"ok": False, "bot_is_admin": False, "title": channel.title, "member_count": None, "error": ""}
    try:
        chat = client._call("getChat", chat_id=channel.channel_id)
        out["title"] = chat.get("title") or channel.title
    except TelegramError as exc:
        out["error"] = f"channel not reachable: {exc}"
    if not out["error"]:
        try:
            out["member_count"] = int(client._call("getChatMemberCount", chat_id=channel.channel_id))
        except TelegramError:
            pass
        try:
            me = client.get_me()
            status = client.get_chat_member(channel.channel_id, me["id"]).get("status")
            out["bot_is_admin"] = status in ("administrator", "creator")
        except TelegramError as exc:
            out["error"] = f"membership check failed: {exc}"
    out["ok"] = out["bot_is_admin"]
    fields = ["bot_is_admin", "last_synced_at"]
    channel.bot_is_admin, channel.last_synced_at = out["bot_is_admin"], timezone.now()
    if out["title"] and out["title"] != channel.title:
        channel.title = out["title"]
        fields.append("title")
    if out["member_count"] is not None:
        channel.member_count = out["member_count"]
        fields.append("member_count")
    channel.save(update_fields=fields)
    return out


def enforced(channels: list) -> list:
    """The channels that count: a store only enforces channels where its bot is admin (checked)."""
    from apps.settings_app.branding import is_store

    return [c for c in channels if c.bot_is_admin] if is_store() else channels
