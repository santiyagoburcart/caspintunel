"""Account-group management for the admin panel (PAMP "Account groups").

Storage is PAMP's: owner_username (unique) + comma-separated member_usernames +
note; the portal reads it through AdminGroup.get_group_for_owner /
get_all_usernames, so every change here is what the owner sees next request.
Validation is a caspintunel addition: owner and new members must be existing
panel admins, the owner is never listed as a member, duplicates are dropped."""
from __future__ import annotations

from django.db import transaction

from .actions import _gate
from .models import AdminGroup, PanelAdmin


class GroupError(ValueError):
    pass


def _members(raw) -> list[str]:
    items = raw if isinstance(raw, (list, tuple)) else str(raw or "").replace("\n", ",").split(",")
    out = []
    for u in items:
        u = str(u).strip()
        if u and u not in out:
            out.append(u)
    return out


@transaction.atomic
def upsert(group_id: int | None, *, owner: str, members, name: str = "", note: str = "") -> AdminGroup:
    _gate()
    owner = (owner or "").strip()
    if not owner:
        raise GroupError("owner_required")
    known = set(PanelAdmin.objects.values_list("username", flat=True))
    g = AdminGroup.objects.select_for_update().filter(pk=group_id).first() if group_id else None
    if group_id and g is None:
        raise GroupError("not_found")
    if owner not in known and not (g and g.owner_username == owner):
        raise GroupError("unknown_owner")
    clash = AdminGroup.objects.filter(owner_username=owner).exclude(pk=g.pk if g else None).first()
    if clash:
        raise GroupError("owner_taken")
    previous = set(g.get_members()) if g else set()
    members = [m for m in _members(members) if m != owner]
    unknown = [m for m in members if m not in known and m not in previous]
    if unknown:
        raise GroupError("unknown_member:" + ",".join(unknown))
    g = g or AdminGroup()
    g.owner_username, g.member_usernames = owner, ",".join(members)
    g.name, g.note = (name or "").strip()[:100], (note or "").strip()[:200]
    g.save()
    return g


def delete(group_id: int) -> bool:
    _gate()
    return AdminGroup.objects.filter(pk=group_id).delete()[0] > 0
