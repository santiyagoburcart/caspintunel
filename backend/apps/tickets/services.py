"""Ticket rules: every state change goes through here (API, bot, beat).

Each function writes the change, a `TicketEvent` for the history and an
`AuditLog` row for staff actions, and queues the notifications for after the
commit (`notify.queue`).
"""
from __future__ import annotations

from datetime import timedelta

from django.core.files.base import File
from django.db import transaction
from django.utils import timezone

from apps.common.models import write_audit

from . import notify, rules
from .models import (
    Channel,
    ClosedBy,
    EventKind,
    Ticket,
    TicketAttachment,
    TicketEvent,
    TicketMessage,
    TicketPriority,
    TicketStatus,
    TicketTopic,
)


class TicketError(Exception):
    """A rule was broken; `code` is stable for the UI, the message is English."""

    def __init__(self, message: str, code: str = "invalid", status: int = 400):
        super().__init__(message)
        self.code, self.status = code, status


def _label(user=None, staff=None) -> str:
    if staff is not None:
        return f"staff:{staff.username}"
    if user is not None:
        return f"user:{user.username}"
    return "system"


def _event(ticket, kind, *, user=None, staff=None, old="", new="", message=None) -> TicketEvent:
    return TicketEvent.objects.create(ticket=ticket, kind=kind, actor_user=user, actor_staff=staff,
                                      actor_label=_label(user, staff), old_value=str(old or "")[:80],
                                      new_value=str(new or "")[:80], message=message)


def _set_status(ticket, status, *, user=None, staff=None, event=True) -> None:
    if ticket.status == status:
        return
    old = ticket.status
    ticket.status = status
    ticket.status_changed_at = timezone.now()
    if event:
        _event(ticket, EventKind.STATUS, user=user, staff=staff, old=old, new=status)


def _add_message(ticket, *, body, files, user=None, staff=None, channel=Channel.SITE, internal=False):
    body = (body or "").strip()
    checked = rules.check_attachments(files)
    if not body and not checked:
        raise TicketError("write a message or attach a file", "empty")
    if len(body) > rules.MAX_BODY:
        raise TicketError(f"message longer than {rules.MAX_BODY} characters", "too_long")
    now = timezone.now()
    msg = TicketMessage.objects.create(
        ticket=ticket, author_user=user, author_staff=staff, body=body, is_internal=internal, channel=channel,
        # the author has obviously read their own message
        read_by_user_at=now if user is not None else None,
        read_by_staff_at=now if staff is not None else None,
    )
    for f, ctype, ext, name in checked:
        att = TicketAttachment(message=msg, original_name=name, content_type=ctype, size=f.size)
        att.file.save(rules.stored_name(ext), File(f), save=False)
        att.save()
    return msg


# --- customer side ------------------------------------------------------------
@transaction.atomic
def open_ticket(user, *, topic_id, subject, body, files=(), service_id=None, order_id=None,
                channel=Channel.SITE) -> Ticket:
    topic = TicketTopic.objects.filter(pk=topic_id, is_active=True).first()
    if topic is None:
        raise TicketError("unknown or inactive topic", "topic")
    if topic.requires_active_service and not rules.has_any_service(user):
        raise TicketError("this topic is for customers — before your first purchase use the pre-purchase topic",
                          "needs_service", 403)
    subject = (subject or "").strip()
    if not subject:
        raise TicketError("subject is required", "subject")
    open_count = Ticket.objects.select_for_update().filter(user=user).exclude(status=TicketStatus.CLOSED).count()
    if open_count >= rules.setting("tickets_max_open_per_user"):
        raise TicketError("too many open tickets — wait for an answer or close one first", "too_many_open", 409)

    service = order = None
    if service_id:
        from apps.panel.models import Service

        service = Service.objects.filter(pk=service_id, user=user).first()
        if service is None:
            raise TicketError("service not found", "service")
    if order_id:
        from apps.orders.models import Order

        order = Order.objects.filter(pk=order_id, user=user).first()
        if order is None:
            raise TicketError("order not found", "order")

    ticket = Ticket.objects.create(user=user, topic=topic, subject=subject[:150], service=service, order=order,
                                   source=channel if channel in (Channel.SITE, Channel.BOT) else Channel.SITE)
    ticket.number = str(100000 + ticket.id)
    ticket.save(update_fields=["number"])
    msg = _add_message(ticket, body=body, files=files, user=user, channel=channel)
    _event(ticket, EventKind.CREATED, user=user, message=msg)
    notify.queue("new_ticket", ticket.id, msg.id)
    return ticket


@transaction.atomic
def user_reply(ticket, user, *, body, files=(), channel=Channel.SITE) -> TicketMessage:
    ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
    if ticket.is_closed:
        raise TicketError("this ticket is closed — reopen it to write again", "closed", 409)
    msg = _add_message(ticket, body=body, files=files, user=user, channel=channel)
    mark_read(ticket, by_user=True)          # answering means the support replies were seen
    _set_status(ticket, TicketStatus.AWAITING_ADMIN, user=user, event=False)
    ticket.last_activity_at = timezone.now()
    ticket.save()
    _event(ticket, EventKind.USER_REPLIED, user=user, message=msg)
    notify.queue("user_reply", ticket.id, msg.id)
    return msg


@transaction.atomic
def user_close(ticket, user) -> Ticket:
    ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
    if ticket.is_closed:
        return ticket
    _close(ticket, kind=ClosedBy.USER, user=user)
    ticket.save()
    notify.queue("changed", ticket.id, None)
    return ticket


@transaction.atomic
def user_reopen(ticket, user) -> Ticket:
    ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
    if not ticket.is_closed:
        return ticket
    days = rules.setting("tickets_reopen_days")
    if not days or not ticket.closed_at or timezone.now() - ticket.closed_at > timedelta(days=days):
        raise TicketError("this ticket can no longer be reopened — please open a new one", "reopen_expired", 409)
    open_count = Ticket.objects.filter(user=user).exclude(status=TicketStatus.CLOSED).count()
    if open_count >= rules.setting("tickets_max_open_per_user"):
        raise TicketError("too many open tickets — close one first", "too_many_open", 409)
    _reopen(ticket, user=user)
    ticket.save()
    notify.queue("user_reply", ticket.id, None)
    return ticket


# --- staff side ------------------------------------------------------------
@transaction.atomic
def open_for_user(user, staff, *, topic_id, subject, body, files=()) -> Ticket:
    """Staff opens a ticket on the customer's behalf (e.g. from a CRM case): the
    first message is from staff, the ticket waits for the customer, no topic gate
    or open limit (they guard what customers may open themselves)."""
    topic = TicketTopic.objects.filter(pk=topic_id).first()
    if topic is None:
        raise TicketError("unknown topic", "topic")
    subject = (subject or "").strip()
    if not subject:
        raise TicketError("subject is required", "subject")
    ticket = Ticket.objects.create(user=user, topic=topic, subject=subject[:150], source=Channel.SITE,
                                   status=TicketStatus.AWAITING_USER, assigned_to=staff, first_response_at=timezone.now())
    ticket.number = str(100000 + ticket.id)
    ticket.save(update_fields=["number"])
    msg = _add_message(ticket, body=body, files=files, staff=staff, channel=Channel.PANEL)
    _event(ticket, EventKind.CREATED, staff=staff, message=msg)
    write_audit(action="ticket.opened_for_user", staff=staff, target=ticket, detail={"user": user.id})
    notify.queue("staff_reply", ticket.id, msg.id)
    return ticket


@transaction.atomic
def staff_reply(ticket, staff, *, body, files=(), internal=False, channel=Channel.PANEL) -> TicketMessage:
    ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
    msg = _add_message(ticket, body=body, files=files, staff=staff, channel=channel, internal=internal)
    mark_read(ticket, by_user=False)         # whoever writes in the ticket has read the customer's messages
    now = timezone.now()
    if internal:
        _event(ticket, EventKind.INTERNAL_NOTE, staff=staff, message=msg)
        write_audit(action="ticket.internal_note", staff=staff, target=ticket, detail={"message": msg.id})
        ticket.save(update_fields=["updated_at"])
        notify.queue("changed", ticket.id, msg.id)          # live refresh for other staff only
        return msg
    if ticket.is_closed:                      # answering a closed ticket reopens it
        _reopen(ticket, staff=staff)
    _set_status(ticket, TicketStatus.AWAITING_USER, staff=staff, event=False)
    if ticket.first_response_at is None:
        ticket.first_response_at = now
    if ticket.assigned_to_id is None:         # whoever answers first owns it
        ticket.assigned_to = staff
        _event(ticket, EventKind.ASSIGNED, staff=staff, new=staff.username)
    ticket.last_activity_at = now
    ticket.save()
    _event(ticket, EventKind.STAFF_REPLIED, staff=staff, message=msg)
    write_audit(action="ticket.replied", staff=staff, target=ticket, detail={"message": msg.id})
    notify.queue("staff_reply", ticket.id, msg.id)
    return msg


@transaction.atomic
def assign(ticket, staff, assignee) -> Ticket:
    ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
    if assignee is not None:
        if not assignee.is_active or not (assignee.is_superadmin or assignee.has_perm("tickets.view")):
            raise TicketError("this staff member cannot handle tickets", "assignee")
        if not rules.staff_covers(assignee, ticket.topic_id):
            raise TicketError("this staff member's topics do not include this ticket's topic", "assignee_scope")
    old = ticket.assigned_to.username if ticket.assigned_to else ""
    if ticket.assigned_to_id == (assignee.id if assignee else None):
        return ticket
    ticket.assigned_to = assignee
    ticket.save(update_fields=["assigned_to", "updated_at"])
    _event(ticket, EventKind.ASSIGNED, staff=staff, old=old, new=assignee.username if assignee else "")
    write_audit(action="ticket.assigned", staff=staff, target=ticket,
                detail={"from": old, "to": assignee.username if assignee else None})
    # an alert for the new owner; assigning yourself / unassigning only refreshes live views
    notify.queue("assigned" if assignee is not None and assignee.id != staff.id else "changed", ticket.id, None)
    return ticket


@transaction.atomic
def set_status(ticket, staff, status) -> Ticket:
    if status not in TicketStatus.values:
        raise TicketError("unknown status", "status")
    ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
    if status == ticket.status:
        return ticket
    if status == TicketStatus.CLOSED:
        _close(ticket, kind=ClosedBy.STAFF, staff=staff)
    elif ticket.is_closed:
        _reopen(ticket, staff=staff, to=status)
    else:
        _set_status(ticket, status, staff=staff)
    ticket.save()
    write_audit(action="ticket.status", staff=staff, target=ticket, detail={"status": status})
    notify.queue("closed" if status == TicketStatus.CLOSED else "changed", ticket.id, None)
    return ticket


@transaction.atomic
def set_priority(ticket, staff, priority) -> Ticket:
    if priority not in TicketPriority.values:
        raise TicketError("unknown priority", "priority")
    ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
    if priority == ticket.priority:
        return ticket
    old, ticket.priority = ticket.priority, priority
    ticket.save(update_fields=["priority", "updated_at"])
    _event(ticket, EventKind.PRIORITY, staff=staff, old=old, new=priority)
    write_audit(action="ticket.priority", staff=staff, target=ticket, detail={"from": old, "to": priority})
    notify.queue("changed", ticket.id, None)
    return ticket


def _close(ticket, *, kind, user=None, staff=None) -> None:
    old = ticket.status
    ticket.status = TicketStatus.CLOSED
    ticket.status_changed_at = ticket.closed_at = timezone.now()
    ticket.closed_by = staff
    ticket.closed_by_kind = kind
    _event(ticket, EventKind.AUTO_CLOSED if kind == ClosedBy.SYSTEM else EventKind.CLOSED,
           user=user, staff=staff, old=old, new=TicketStatus.CLOSED)


def _reopen(ticket, *, user=None, staff=None, to=None) -> None:
    to = to or (TicketStatus.AWAITING_ADMIN if user is not None else TicketStatus.OPEN)
    ticket.status = to
    ticket.status_changed_at = ticket.last_activity_at = timezone.now()
    ticket.closed_at = None
    ticket.closed_by = None
    ticket.closed_by_kind = ""
    _event(ticket, EventKind.REOPENED, user=user, staff=staff, old=TicketStatus.CLOSED, new=to)


def auto_close_stale() -> int:
    """Beat: tickets waiting on the customer for `tickets_auto_close_days` → closed."""
    cutoff = timezone.now() - timedelta(days=rules.setting("tickets_auto_close_days"))
    done = 0
    for pk in Ticket.objects.filter(status=TicketStatus.AWAITING_USER, status_changed_at__lt=cutoff) \
            .values_list("id", flat=True):
        with transaction.atomic():
            t = Ticket.objects.select_for_update().get(pk=pk)
            if t.status != TicketStatus.AWAITING_USER or t.status_changed_at >= cutoff:
                continue
            _close(t, kind=ClosedBy.SYSTEM)
            t.save()
            notify.queue("auto_closed", t.id, None)
            done += 1
    return done


def mark_read(ticket, *, by_user: bool) -> int:
    """The other side's messages in this ticket are now read."""
    now = timezone.now()
    qs = ticket.messages.all()
    if by_user:
        return qs.filter(author_staff__isnull=False, is_internal=False, read_by_user_at__isnull=True) \
                 .update(read_by_user_at=now)
    return qs.filter(author_user__isnull=False, read_by_staff_at__isnull=True).update(read_by_staff_at=now)
