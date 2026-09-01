"""Forced-channel-join + phone-sharing gate for the sales bot (flowchart 1.7)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from apps.settings_app.utils import get_setting

from .config import sales_client
from .models import RequiredChannel

log = logging.getLogger("caspintunel")


@dataclass
class GateResult:
    ok: bool
    missing_channels: list = field(default_factory=list)
    need_phone: bool = False


def missing_channel_memberships(telegram_id: int, client=None) -> list[RequiredChannel]:
    if not get_setting("force_channel_join", False):
        return []
    channels = list(RequiredChannel.objects.filter(is_active=True))
    if not channels:
        return []
    client = client or sales_client()
    if client is None:
        return channels  # bot unconfigured -> be conservative
    missing = []
    for channel in channels:
        if not client.is_member(channel.channel_id, telegram_id):
            missing.append(channel)
    return missing


def needs_phone(user) -> bool:
    return bool(get_setting("force_share_phone", False)) and not user.phone


def check_access(user, telegram_id: int, client=None) -> GateResult:
    missing = missing_channel_memberships(telegram_id, client=client)
    phone = needs_phone(user)
    return GateResult(ok=(not missing and not phone), missing_channels=missing, need_phone=phone)
