"""Ticket notifications — run in Celery after the change is committed.

Customer (staff replied / ticket closed): `notifications.dispatch.notify_user`
→ site bell (real-time), sales-bot message, email.

Staff (new ticket / customer replied / assigned to them): the assignee, or — if
nobody owns the ticket yet — every active staff member whose permission and
topic scope cover it (`rules.ticket_staff`): a real-time push with their badge
count on `/ws/admin/tickets/`, a bot DM when their Telegram is linked, and an
email when they have one. Every channel is isolated: a failure is logged and
never blocks the others.
"""
from __future__ import annotations

import html
import logging

from celery import shared_task
from django.db import transaction

log = logging.getLogger("caspintunel")

STAFF_GROUP = "staff_tickets_{}"
SNIPPET = 300


def queue(kind: str, ticket_id: int, message_id: int | None) -> None:
    transaction.on_commit(lambda: notify_ticket_task.delay(kind, ticket_id, message_id))


@shared_task(ignore_result=True)
def notify_ticket_task(kind: str, ticket_id: int, message_id: int | None = None):
    from .models import Ticket, TicketMessage

    ticket = Ticket.objects.select_related("user", "topic", "assigned_to").filter(pk=ticket_id).first()
    if ticket is None:
        return {"skipped": "ticket gone"}
    msg = TicketMessage.objects.filter(pk=message_id).first() if message_id else None
    if kind in ("staff_reply", "closed", "auto_closed"):
        return {"user": _to_user(kind, ticket, msg)}
    if kind in ("new_ticket", "user_reply", "assigned"):
        return {"staff": _to_staff(kind, ticket, msg)}
    return {"skipped": kind}


def _snippet(msg) -> str:
    body = (msg.body if msg else "") or ""
    return body if len(body) <= SNIPPET else body[:SNIPPET] + "…"


# --- customer -----------------------------------------------------------------
def _to_user(kind, ticket, msg) -> str:
    from apps.notifications.dispatch import notify_user

    n = ticket.number
    if kind == "staff_reply":
        title, title_en = f"پاسخ جدید به تیکت #{n}", f"New reply to ticket #{n}"
        body = body_en = f"{ticket.subject}\n\n{_snippet(msg)}"
        channels = dict(via_site=True, via_bot=True, via_email=True)
    else:
        title, title_en = f"تیکت #{n} بسته شد", f"Ticket #{n} was closed"
        body = f"{ticket.subject}\nاگر هنوز مشکلی هست، می‌توانید تیکت را دوباره باز کنید."
        body_en = f"{ticket.subject}\nIf the problem is not solved yet, you can reopen the ticket."
        channels = dict(via_site=True, via_bot=False, via_email=False)
    if ticket.user.deleted_at:
        return "user deleted"
    notify_user(ticket.user, title=title, body=body, title_en=title_en, body_en=body_en, **channels)
    return "sent"


# --- staff ----------------------------------------------------------------------
def recipients(ticket) -> list:
    from . import rules

    a = ticket.assigned_to
    if a is not None and a.is_active and (a.is_superadmin or a.has_perm("tickets.view")) \
            and rules.staff_covers(a, ticket.topic_id):
        return [a]
    return rules.ticket_staff(ticket.topic_id)


def badge_count(staff) -> int:
    """Tickets waiting for staff that are this person's to answer: in their topic
    scope, open / awaiting admin, and unassigned or assigned to them."""
    from django.db.models import Q

    from . import rules
    from .models import TicketStatus

    return rules.staff_queryset(staff).filter(
        status__in=(TicketStatus.OPEN, TicketStatus.AWAITING_ADMIN),
    ).filter(Q(assigned_to__isnull=True) | Q(assigned_to=staff)).count()


def _texts(kind, ticket, msg) -> tuple[str, str]:
    n, who, topic = ticket.number, ticket.user.username, ticket.topic.name_fa
    if kind == "new_ticket":
        head = f"🎫 تیکت جدید #{n} — {topic}"
    elif kind == "assigned":
        head = f"📌 تیکت #{n} به شما سپرده شد — {topic}"
    else:
        head = f"💬 پاسخ کاربر در تیکت #{n} — {topic}"
    return head, f"{ticket.subject}\n{who}\n\n{_snippet(msg)}".strip()


def _to_staff(kind, ticket, msg) -> int:
    title, body = _texts(kind, ticket, msg)
    sent = 0
    for staff in recipients(ticket):
        _push(staff, kind, ticket)
        if staff.telegram_id:
            _bot(staff, title, body)
        if staff.email:
            _email(staff, title, body)
        sent += 1
    return sent


def _push(staff, kind, ticket) -> None:
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(STAFF_GROUP.format(staff.id), {
            "type": "tickets.event",
            "payload": {"event": kind, "ticket_id": ticket.id, "number": ticket.number,
                        "subject": ticket.subject, "badge": badge_count(staff)},
        })
    except Exception as exc:  # noqa: BLE001
        log.warning("ticket push to staff %s failed: %s", staff.id, exc)


def _bot(staff, title, body) -> None:
    try:
        from apps.telegram.config import sales_client

        client = sales_client()
        if client is not None:
            client.send_message(staff.telegram_id, f"<b>{html.escape(title)}</b>\n\n{html.escape(body)}")
    except Exception as exc:  # noqa: BLE001
        log.warning("ticket bot DM to staff %s failed: %s", staff.id, exc)


def _email(staff, title, body) -> None:
    try:
        from django.conf import settings
        from django.core.mail import send_mail

        from apps.common.mail import mail_configured

        if mail_configured():
            send_mail(title, body, settings.DEFAULT_FROM_EMAIL, [staff.email], fail_silently=False)
    except Exception as exc:  # noqa: BLE001
        log.warning("ticket email to staff %s failed: %s", staff.id, exc)
