"""Admin data-limit history (caspintunel addition, docs/agency.md → "Limit history").

Every way a limit can change is recorded here, with the old and new value, who did it
and from where — our agency panel (create / set / add / reduce / remove) and PasarGuard
directly (the sync compares the panel's value with ours before it overwrites it) —
plus an `agency.limit_changed` audit entry. Never touches PAMP's numbers.
"""
from __future__ import annotations

from django.utils import timezone

from apps.common.models import write_audit

from .models import AdminLimitChange
from .notes import to_fa

GIB = 1024 ** 3


def fmt(b) -> str:
    if b is None:
        return "?"
    if not b or b <= 0:
        return "Unlimited"
    return f"{b / GIB:,.1f} GB ({b / 1024 ** 4:,.3f} TB)"


def record(username: str, old, new, *, action: str, source: str = "panel", by="", note: str = "",
           ledger_entry=None, at=None, audit: bool = True) -> AdminLimitChange:
    old = None if old is None else int(old or 0)
    new = int(new or 0)
    staff_obj = by if hasattr(by, "username") else None
    label = getattr(by, "username", None) or str(by or "")
    row = AdminLimitChange.objects.create(
        admin_username=username, old_limit_bytes=old, new_limit_bytes=new, action=action, source=source,
        staff=label[:150], note=note[:255], ledger_entry=ledger_entry, created_at=at or timezone.now())
    if audit:
        if staff_obj is None and label:
            from apps.accounts.models import Staff

            staff_obj = Staff.objects.filter(username=label).first()
        log = write_audit(action="agency.limit_changed", staff=staff_obj, target=None, detail={
            "admin": username, "action": action, "source": source,
            "old_limit_bytes": old, "new_limit_bytes": new, "old": fmt(old), "new": fmt(new),
            "ledger_entry": getattr(ledger_entry, "id", None), "note": note[:200]})
        if staff_obj is None and label and hasattr(log, "staff_label"):
            log.staff_label = label[:150]
            log.save(update_fields=["staff_label"])
    return row



def history(username: str) -> list[dict]:
    out = []
    for r in AdminLimitChange.objects.filter(admin_username=username).select_related("ledger_entry"):
        le = r.ledger_entry
        out.append({
            "id": r.id, "at": r.created_at, "action": r.action, "source": r.source, "staff": r.staff, "note": r.note,
            "note_fa": to_fa(r.note),
            "old_limit_bytes": r.old_limit_bytes, "new_limit_bytes": r.new_limit_bytes,
            "old_fmt": fmt(r.old_limit_bytes), "new_fmt": fmt(r.new_limit_bytes),
            "delta_bytes": (r.new_limit_bytes - r.old_limit_bytes) if (r.old_limit_bytes and r.new_limit_bytes) else None,
            "ledger": ({"id": le.id, "amount": str(le.amount), "gb": str(le.gb) if le.gb is not None else None,
                        "voided": le.voided} if le else None),
        })
    return out
