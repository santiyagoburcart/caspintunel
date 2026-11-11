"""v1.54 — agency admins and group managers are never hard-deleted on our side.

* An admin that disappears from PasarGuard (the sync — the ONE deliberate deviation from PAMP's verbatim code, PORTING.md)
  or that our staff delete in the Agency panel is ARCHIVED («حذف‌شده», `archived_at` + reason): the default manager
  `PanelAdmin.objects` hides it from the sync, enforcement and every active list; everything it ever had stays — ledger,
  invoices, payments, allocations, prices, limit history, usage snapshots, volume requests, notices, its group link.
  Its balance stays visible and can still be paid / adjusted by our staff, and its group manager's «پرداخت کل بدهی»
  still includes it. Staff see it under the «بایگانی» filter; group managers in their admin list too.
* The same username back on PasarGuard (the next sync, or created again in our panel) RESTORES the row — history continues.
* A deleted group-manager staff account → the manager is deactivated + archived instead (its requests, payments, notices,
  activity stay); its groups pay directly again (`billing.manager_of_group` counts active managers only).
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.common.models import write_audit

log = logging.getLogger("caspintunel")

PANEL_MISSING, DELETED = "panel_missing", "deleted"
REASONS_FA = {PANEL_MISSING: "دیگر روی پنل نیست", DELETED: "حذف از پنل نمایندگی"}


class Archived(Exception):
    """An action on an archived admin (limit, volume, request …)."""

    en = "this admin is archived (deleted) — its history and balance stay, but nothing can be changed on the panel"
    fa = "این ادمین بایگانی (حذف) شده است — سابقه و مانده‌اش می‌ماند ولی روی پنل تغییری داده نمی‌شود"


def get_any(username: str):
    """The admin row, archived or not (None when it never existed)."""
    from .models import PanelAdmin

    return PanelAdmin.all_objects.filter(username=username).first()


def is_archived(username: str) -> bool:
    from .models import PanelAdmin

    return PanelAdmin.all_objects.filter(username=username, archived_at__isnull=False).exists()


def archive(usernames, *, reason: str, by: str = "") -> list[str]:
    """Archive the given ACTIVE admins (nothing else is touched). Returns the usernames archived."""
    from .models import PanelAdmin

    names = sorted(set(PanelAdmin.objects.filter(username__in=list(usernames)).values_list("username", flat=True)))
    if not names:
        return []
    now = timezone.now()
    PanelAdmin.all_objects.filter(username__in=names, archived_at__isnull=True).update(
        archived_at=now, archived_reason=reason, archived_by=(by or "")[:150])
    for n in names:
        write_audit(action="agency.admin_archived", staff=None, target=None,
                    detail={"admin": n, "reason": reason, "by": by})
    log.info("agency: archived %s (%s)", ", ".join(names), reason)
    return names


def restore(usernames, *, by: str = "") -> list[str]:
    """Back on PasarGuard / created again: the archived row becomes active again (history continues)."""
    from .models import PanelAdmin

    names = sorted(set(PanelAdmin.all_objects.filter(username__in=list(usernames), archived_at__isnull=False)
                       .values_list("username", flat=True)))
    if not names:
        return []
    PanelAdmin.all_objects.filter(username__in=names).update(archived_at=None, archived_reason="", archived_by="")
    for n in names:
        write_audit(action="agency.admin_restored", staff=None, target=None, detail={"admin": n, "by": by})
    log.info("agency: restored %s", ", ".join(names))
    return names


def guard(username: str) -> None:
    """Raise Archived for an archived admin (actions that would touch PasarGuard / give volume)."""
    if is_archived(username):
        raise Archived(username)


@transaction.atomic
def deactivate_manager(m, *, by: str = "") -> None:
    """A group manager's staff account is being deleted: keep the manager (and its history), switch it off."""
    from .models import GroupManager

    GroupManager.objects.filter(pk=m.pk).update(is_active=False, archived_at=timezone.now())
    write_audit(action="agency.manager_archived", staff=None, target=None,
                detail={"manager": m.username, "by": by, "groups": list(m.assignments.values_list("group_id", flat=True))})


def row_info(a) -> dict:
    return {"archived": a.archived_at is not None, "archived_at": a.archived_at, "archived_reason": a.archived_reason,
            "archived_reason_fa": REASONS_FA.get(a.archived_reason, ""), "archived_by": a.archived_by}
