"""Permanent delete ("purge") of a soft-deleted user — the ONE implementation.

A purge removes the person, but never money: orders and payments stay (Accounting,
Analytics and every report keep the same totals). The User row itself stays as an
anonymous placeholder because orders point at it:

  username → «کاربر حذف‌شده #<id>», no name / phone / email / Telegram / bank card /
  notes, unusable password, inactive, purged_at set.

Removed: services (and, if asked, their PasarGuard accounts), tickets with messages
and attachment files, CRM data (profile, notes, follow-up cases, timeline, personal
discount codes), notifications, login tokens, the Telegram link, and the deletion
archives (they hold the original profile). There is no automatic purge yet; one must
call `purge_user` too, never a copy of it.

PasarGuard goes first: every account is read before anything is deleted, so an
unreachable panel stops the purge with nothing changed. The audit entry carries
counts only — no personal data.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.common.models import write_audit

from .models import DeletedUserArchive, Staff, User

log = logging.getLogger("caspintunel")

PURGED_NAME = "کاربر حذف‌شده #{id}"


class PurgeError(Exception):
    def __init__(self, message: str, code: str = "invalid", *, panel: list | None = None):
        super().__init__(message)
        self.code = code
        self.panel = panel or []


def purged_username(user_id: int) -> str:
    return PURGED_NAME.format(id=user_id)


def _check_user(user: User) -> None:
    if user.purged_at is not None:
        raise PurgeError("this user was already permanently deleted", "already_purged")
    if user.deleted_at is None:
        raise PurgeError("only a user in the trash (soft-deleted) can be permanently deleted", "not_deleted")


def counts(user: User) -> dict:
    """What a purge removes / keeps for this user (numbers only)."""
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

    from apps.crm.models import CrmEvent, CustomerNote, CustomerProfile, DiscountCode, FollowUpCase
    from apps.notifications.models import Notification, NotificationDelivery
    from apps.orders.models import Order
    from apps.panel.models import Service
    from apps.payments_sms.models import Payment
    from apps.tickets.models import Ticket, TicketAttachment, TicketMessage

    tickets = Ticket.objects.filter(user=user)
    return {
        "services": Service.objects.filter(user=user).count(),
        "tickets": tickets.count(),
        "ticket_messages": TicketMessage.objects.filter(ticket__in=tickets).count(),
        "ticket_attachments": TicketAttachment.objects.filter(message__ticket__in=tickets).count(),
        "crm": {"profile": CustomerProfile.objects.filter(user=user).count(),
                "notes": CustomerNote.objects.filter(user=user).count(),
                "cases": FollowUpCase.objects.filter(user=user).count(),
                "events": CrmEvent.objects.filter(user=user).count(),
                "discount_codes": DiscountCode.objects.filter(user=user).count()},
        "notifications": (Notification.objects.filter(target_user=user).count()
                          + NotificationDelivery.objects.filter(user=user).count()),
        "tokens": OutstandingToken.objects.filter(user=user).count(),
        "telegram_linked": bool(user.telegram_id or user.deletion_archives.exclude(original_telegram_id=None).exists()),
        "archives": user.deletion_archives.count(),
        "kept_orders": Order.objects.filter(user=user).count(),
        "kept_payments": Payment.objects.filter(order__user=user).count(),
    }


def panel_accounts(user: User) -> list[dict]:
    """Each service's PasarGuard account: exists True / False, or None + error when the panel can't tell."""
    from apps.panel.exceptions import PanelNotFound
    from apps.panel.models import Service
    from apps.panel.services import client_for

    out = []
    for svc in Service.objects.filter(user=user).select_related("panel").order_by("id"):
        row = {"service_id": svc.id, "panel_username": svc.panel_username, "panel": svc.panel.name,
               "exists": None, "error": ""}
        try:
            client_for(svc.panel).get_user(svc.panel_username)
            row["exists"] = True
        except PanelNotFound:
            row["exists"] = False
        except Exception as exc:  # noqa: BLE001 — unreachable / auth: unknown, the purge will refuse
            row["error"] = f"{type(exc).__name__}: {exc}"[:300]
        out.append(row)
    return out


def preview(user: User, *, check_panel: bool = True) -> dict:
    _check_user(user)
    accounts = panel_accounts(user) if check_panel else []
    return {"user_id": user.id, "removes": counts(user), "panel_accounts": accounts,
            "panel_existing": sum(1 for a in accounts if a["exists"]),
            "panel_unknown": sum(1 for a in accounts if a["exists"] is None)}


def _delete_on_panel(user: User) -> list[dict]:
    """Delete every existing PasarGuard account of the user, verified by reading back.
    All accounts are read first: any doubt → PurgeError before a single delete."""
    from apps.panel.exceptions import PanelNotFound
    from apps.panel.models import Service
    from apps.panel.services import client_for

    accounts = panel_accounts(user)
    unknown = [a for a in accounts if a["exists"] is None]
    if unknown:
        a = unknown[0]
        raise PurgeError(f"PasarGuard: {a['panel_username']} on {a['panel']} — {a['error']} — nothing was deleted",
                         "panel_error", panel=accounts)
    svcs = {s.id: s for s in Service.objects.filter(user=user).select_related("panel")}
    done = []
    for a in accounts:
        if not a["exists"]:
            a["result"] = "not on the panel"
            continue
        svc = svcs[a["service_id"]]
        client = client_for(svc.panel)
        try:
            try:
                client.delete_user(svc.panel_username)
            except PanelNotFound:
                pass
            try:
                client.get_user(svc.panel_username)
            except PanelNotFound:
                a["result"] = "deleted"
                done.append(a["panel_username"])
                continue
            raise PurgeError(f"PasarGuard: {svc.panel_username} still exists after the delete", "panel_error")
        except PurgeError as exc:
            exc.panel = accounts
            if done:
                exc.args = (f"{exc.args[0]} — already deleted on PasarGuard: {', '.join(done)}; "
                            "nothing was deleted here, try again",)
            else:
                exc.args = (f"{exc.args[0]} — nothing was deleted",)
            raise
        except Exception as exc:  # noqa: BLE001
            msg = f"PasarGuard: {svc.panel_username} — {type(exc).__name__}: {exc}"
            msg += (f" — already deleted on PasarGuard: {', '.join(done)}; nothing was deleted here, try again"
                    if done else " — nothing was deleted")
            raise PurgeError(msg, "panel_error", panel=accounts) from exc
    return accounts


def purge_user(user: User, *, staff, delete_on_panel: bool) -> dict:
    """Permanently delete a soft-deleted user (see module doc). Raises PurgeError."""
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

    from apps.crm.models import CrmEvent, CustomerNote, CustomerProfile, DiscountCode, FollowUpCase
    from apps.notifications.models import Notification, NotificationDelivery
    from apps.panel.models import Service
    from apps.tickets.models import Ticket, TicketAttachment

    _check_user(user)
    removed = counts(user)
    panel = _delete_on_panel(user) if delete_on_panel and removed["services"] else []

    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user.pk)
        _check_user(user)
        tickets = Ticket.objects.filter(user=user)
        files = [a.file.name for a in TicketAttachment.objects.filter(message__ticket__in=tickets) if a.file]
        storage = TicketAttachment._meta.get_field("file").storage
        tickets.delete()
        CrmEvent.objects.filter(user=user).delete()
        CustomerNote.objects.filter(user=user).delete()
        FollowUpCase.objects.filter(user=user).delete()
        DiscountCode.objects.filter(user=user).delete()
        CustomerProfile.objects.filter(user=user).delete()
        Notification.objects.filter(target_user=user).delete()
        NotificationDelivery.objects.filter(user=user).delete()
        Service.objects.filter(user=user).delete()          # orders keep their rows (service → null)
        OutstandingToken.objects.filter(user=user).delete()  # + their blacklist rows
        DeletedUserArchive.objects.filter(user=user).delete()

        user.username = purged_username(user.pk)
        user.name = ""
        user.phone = ""
        user.email = None
        user.email_verified = False
        user.telegram_id = None
        user.telegram_username = None
        user.bank_card_number = None
        user.admin_note = ""
        user.delete_reason = ""
        user.referred_by = None
        user.is_active = False
        user.set_unusable_password()
        user.purged_at = timezone.now()
        user.purged_by = staff if isinstance(staff, Staff) else None
        user.save()

        summary = {"user_id": user.pk, "removed": removed, "delete_on_panel": bool(delete_on_panel),
                   "panel_deleted": sum(1 for a in panel if a.get("result") == "deleted"),
                   "panel_missing": sum(1 for a in panel if a.get("result") == "not on the panel"),
                   "panel_kept": 0 if delete_on_panel else removed["services"]}
        write_audit(action="user.purged", staff=staff, target=user, detail=summary)

        def _rm_files():
            for name in files:
                try:
                    storage.delete(name)
                except Exception as exc:  # noqa: BLE001
                    log.warning("purge user %s: attachment file not removed: %s", user.pk, exc)
        transaction.on_commit(_rm_files)
    return summary
