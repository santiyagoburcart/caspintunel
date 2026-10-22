"""CRM data. The customer is `accounts.User`; everything else (services, orders,
payments, tickets, notifications) is read from its own app — this app only adds
what CRM needs on top: a profile (stage, owner, tags), notes, follow-up cases
with a configurable reason list, message templates and an event log for the
timeline (stage changes and staff actions)."""
from __future__ import annotations

from django.db import models
from django.utils import timezone


class Stage(models.TextChoices):
    LEAD = "lead", "Lead"                 # registered, never bought
    NEW = "new", "New"                    # first purchase within the "new" window
    ACTIVE = "active", "Active"
    AT_RISK = "at_risk", "At risk"        # live service but inactive / expiring / almost used up
    EXPIRED = "expired", "Expired"        # no live service, recently
    CHURNED = "churned", "Churned"        # no live service for crm_churn_days
    WON_BACK = "won_back", "Won back"     # bought again after expired / churned


class Tag(models.Model):
    name = models.CharField(max_length=40, unique=True)
    color = models.CharField(max_length=16, default="#1464BA")

    class Meta:
        db_table = "crm_tag"
        ordering = ("name",)


class CustomerProfile(models.Model):
    user = models.OneToOneField("accounts.User", on_delete=models.CASCADE, related_name="crm")
    stage = models.CharField(max_length=10, choices=Stage.choices, default=Stage.LEAD)      # last computed
    stage_override = models.CharField(max_length=10, choices=Stage.choices, blank=True, default="")
    stage_changed_at = models.DateTimeField(default=timezone.now)
    owner = models.ForeignKey("accounts.Staff", null=True, blank=True, on_delete=models.SET_NULL, related_name="crm_customers")
    tags = models.ManyToManyField(Tag, blank=True, related_name="customers", db_table="crm_profile_tag")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "crm_customer_profile"

    @property
    def effective_stage(self) -> str:
        return self.stage_override or self.stage


class CustomerNote(models.Model):
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="crm_notes")
    staff = models.ForeignKey("accounts.Staff", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    staff_label = models.CharField(max_length=64, blank=True, default="")
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "crm_customer_note"
        ordering = ("-created_at",)


class CaseReason(models.Model):
    """Why a customer is inactive — configurable list."""
    name_fa = models.CharField(max_length=80)
    name_en = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        db_table = "crm_case_reason"
        ordering = ("sort_order", "id")


class CaseKind(models.TextChoices):
    NO_CONNECTION = "no_connection", "Active service, no connection"
    NEVER_CONNECTED = "never_connected", "Purchased, never connected"
    LEAD = "lead", "Lead follow-up"
    MANUAL = "manual", "Manual"


class CaseStatus(models.TextChoices):
    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"


class Outcome(models.TextChoices):
    RESOLVED = "resolved", "Resolved"
    STILL_INACTIVE = "still_inactive", "Still inactive"
    LOST = "lost", "Lost"


class FollowUpCase(models.Model):
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="crm_cases")
    service = models.ForeignKey("panel.Service", null=True, blank=True, on_delete=models.SET_NULL, related_name="crm_cases")
    kind = models.CharField(max_length=16, choices=CaseKind.choices)
    status = models.CharField(max_length=8, choices=CaseStatus.choices, default=CaseStatus.OPEN, db_index=True)
    outcome = models.CharField(max_length=16, choices=Outcome.choices, blank=True, default="")
    reason = models.ForeignKey(CaseReason, null=True, blank=True, on_delete=models.SET_NULL, related_name="cases")
    notes = models.TextField(blank=True, default="")
    assigned_to = models.ForeignKey("accounts.Staff", null=True, blank=True, on_delete=models.SET_NULL, related_name="crm_cases")
    ticket = models.ForeignKey("tickets.Ticket", null=True, blank=True, on_delete=models.SET_NULL, related_name="crm_cases")
    # detection snapshot: last connection / purchase time the case was opened for
    last_online_at = models.DateTimeField(null=True, blank=True)
    inactive_since = models.DateTimeField(null=True, blank=True)
    auto_message_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey("accounts.Staff", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    closed_by_system = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "crm_followup_case"
        ordering = ("-opened_at",)
        indexes = [models.Index(fields=["user", "status"]), models.Index(fields=["service", "status"])]


class MessageTemplate(models.Model):
    """Editable message for follow-ups (rendered with {name}, {username}, {service}, {site}, {guide})."""
    title = models.CharField(max_length=80)
    body_fa = models.TextField()
    body_en = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        db_table = "crm_message_template"
        ordering = ("sort_order", "id")


class EventKind(models.TextChoices):
    STAGE = "stage", "Stage changed"
    OWNER = "owner", "Owner changed"
    TAGS = "tags", "Tags changed"
    NOTE = "note", "Note added"
    CASE_OPENED = "case_opened", "Case opened"
    CASE_UPDATED = "case_updated", "Case updated"
    CASE_CLOSED = "case_closed", "Case closed"
    MESSAGE = "message", "Message sent"
    TICKET = "ticket", "Ticket opened / linked"


class CrmEvent(models.Model):
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="crm_events")
    kind = models.CharField(max_length=16, choices=EventKind.choices)
    actor_label = models.CharField(max_length=80, blank=True, default="")    # staff:<name> | system
    detail = models.JSONField(default=dict, blank=True)
    case = models.ForeignKey(FollowUpCase, null=True, blank=True, on_delete=models.SET_NULL, related_name="events")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "crm_event"
        ordering = ("-created_at", "-id")
