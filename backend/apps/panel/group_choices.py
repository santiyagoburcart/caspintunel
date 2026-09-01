"""
Best-effort list of (group_id, label) choices for admin multi-selects.

Tries the live panel (cached 5 min); falls back to the known static id set so
the admin still works when the panel is unreachable.
"""
from __future__ import annotations

import logging

from django.core.cache import cache

from .constants import ALL_PANEL_GROUP_IDS

log = logging.getLogger("caspintunel")
_CACHE_KEY = "panel:group_choices"


def get_group_choices() -> list[tuple[int, str]]:
    cached = cache.get(_CACHE_KEY)
    if cached:
        return cached

    choices = [(gid, f"Group {gid}") for gid in ALL_PANEL_GROUP_IDS]
    try:
        from .services import client_for, get_active_panel

        panel = get_active_panel()
        if panel:
            groups = client_for(panel).list_groups()
            live = [
                (int(g["id"]), f"{g['id']} — {g.get('name', '')}".strip(" —"))
                for g in groups
                if isinstance(g, dict) and g.get("id") is not None
            ]
            if live:
                choices = live
    except Exception as exc:  # noqa: BLE001 - admin must not break on panel outage
        log.warning("group choices: falling back to static list (%s)", exc)

    cache.set(_CACHE_KEY, choices, 300)
    return choices
