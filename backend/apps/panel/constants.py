"""
Panel group ids currently configured on the production panel (pas.hunaex.shop),
as reported by `python manage.py panel_check`:

    id=5  Mix tun+cdn
    id=6  CDN ++
    id=8  tunel +
    id=10 wirgard

Used only as the *default* for new plans and for a freshly-seeded panel row.
Operators change the set per-plan (`Plan.group_ids`) or per-panel
(`Panel.default_group_ids`) from the Django admin at any time — no code change.
"""

ALL_PANEL_GROUP_IDS = [5, 6, 8, 10]


def default_group_ids() -> list[int]:
    """Callable default for JSONField (never share a mutable literal)."""
    return list(ALL_PANEL_GROUP_IDS)
