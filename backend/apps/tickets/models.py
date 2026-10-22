"""Support tickets.

A customer (`accounts.User`) opens a ticket in a `TicketTopic`; staff answer it
from the panel inbox. Every change is also written as a `TicketEvent`, so the
history (who replied / assigned / changed status / closed / reopened) survives
later edits. Attachments are private media: served only through
`views.AttachmentFileView` (X-Accel-Redirect), never from `/media/tickets/`.
"""
from __future__ import annotations

from django.db import models
from django.utils import timezone


class TicketTopic(models.Model):
    name_fa = models.CharField(max_length=80)
    name_en = models.CharField(max_length=80)
    description_fa = models.CharField(max_length=255, blank=True, default="")
    description_en = models.CharField(max_length=255, blank=True, default="")
    # False = "pre-purchase": also open to users without an active service
    requires_active_service = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
    # staff limited to some topics see only those; a staff member with no topic
    # here at all is unrestricted (see scopes.visible_topic_ids)
    staff = models.ManyToManyField("accounts.Staff", blank=True, related_name="ticket_topics",
                                   db_table="ticket_staff_topic")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ticket_topic"
        ordering = ("sort_order", "id")

    def __str__(self) -> str:
        return self.name_en or self.name_fa


class TicketStatus(models.TextChoices):
    OPEN = "open", "Open"                          # new, nobody answered yet
    AWAITING_ADMIN = "awaiting_admin", "Awaiting admin"
    AWAITING_USER = "awaiting_user", "Awaiting user"
    ON_HOLD = "on_hold", "On hold"
    CLOSED = "closed", "Closed"


class TicketPriority(models.TextChoices):
    LOW = "low", "Low"
    NORMAL = "normal", "Normal"
    HIGH = "high", "High"
    URGENT = "urgent", "Urgent"


class Channel(models.TextChoices):
    SITE = "site", "Site"
    BOT = "bot", "Bot"
    PANEL = "panel", "Admin panel"


class ClosedBy(models.TextChoices):
    USER = "user", "User"
    STAFF = "staff", "Staff"
    SYSTEM = "system", "System (auto-close)"


class Ticket(models.Model):
    number = models.CharField(max_length=16, unique=True, null=True, blank=True)   # set right after insert
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="tickets")
    topic = models.ForeignKey(TicketTopic, on_delete=models.PROTECT, related_name="tickets")
    subject = models.CharField(max_length=150)
    status = models.CharField(max_length=16, choices=TicketStatus.choices, default=TicketStatus.OPEN, db_index=True)
    priority = models.CharField(max_length=8, choices=TicketPriority.choices, default=TicketPriority.NORMAL)
    assigned_to = models.ForeignKey("accounts.Staff", null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="assigned_tickets")
    service = models.ForeignKey("panel.Service", null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="tickets")
    order = models.ForeignKey("orders.Order", null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="tickets")
    source = models.CharField(max_length=8, choices=Channel.choices, default=Channel.SITE)
    first_response_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(default=timezone.now, db_index=True)
    status_changed_at = models.DateTimeField(default=timezone.now)
    closed_by = models.ForeignKey("accounts.Staff", null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="closed_tickets")
    closed_by_kind = models.CharField(max_length=8, choices=ClosedBy.choices, blank=True, default="")
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ticket"
        ordering = ("-last_activity_at",)
        indexes = [models.Index(fields=["user", "status"]), models.Index(fields=["topic", "status"])]

    def __str__(self) -> str:
        return f"#{self.number} {self.subject}"

    @property
    def is_closed(self) -> bool:
        return self.status == TicketStatus.CLOSED


class TicketMessage(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="messages")
    author_user = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="ticket_messages")
    author_staff = models.ForeignKey("accounts.Staff", null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="ticket_messages")
    body = models.TextField(blank=True, default="")
    is_internal = models.BooleanField(default=False)      # staff-only note, never shown to the user
    channel = models.CharField(max_length=8, choices=Channel.choices, default=Channel.SITE)
    read_by_user_at = models.DateTimeField(null=True, blank=True)
    read_by_staff_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ticket_message"
        ordering = ("created_at", "id")

    @property
    def from_staff(self) -> bool:
        return self.author_staff_id is not None


class TicketAttachment(models.Model):
    message = models.ForeignKey(TicketMessage, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="tickets/%Y/%m/")
    original_name = models.CharField(max_length=150)
    content_type = models.CharField(max_length=64)
    size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ticket_attachment"
        ordering = ("id",)


class EventKind(models.TextChoices):
    CREATED = "created", "Created"
    USER_REPLIED = "user_replied", "User replied"
    STAFF_REPLIED = "staff_replied", "Staff replied"
    INTERNAL_NOTE = "internal_note", "Internal note"
    ASSIGNED = "assigned", "Assigned"
    STATUS = "status", "Status changed"
    PRIORITY = "priority", "Priority changed"
    CLOSED = "closed", "Closed"
    REOPENED = "reopened", "Reopened"
    AUTO_CLOSED = "auto_closed", "Auto-closed"


class TicketEvent(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=16, choices=EventKind.choices)
    actor_user = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    actor_staff = models.ForeignKey("accounts.Staff", null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    # kept as text so the history still reads after the staff/user row is gone
    actor_label = models.CharField(max_length=80, blank=True, default="")
    old_value = models.CharField(max_length=80, blank=True, default="")
    new_value = models.CharField(max_length=80, blank=True, default="")
    message = models.ForeignKey(TicketMessage, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ticket_event"
        ordering = ("created_at", "id")
