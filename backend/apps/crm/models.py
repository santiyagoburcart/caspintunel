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


class Category(models.TextChoices):
    INACTIVITY = "inactivity", "Inactivity follow-up"
    WINBACK = "winback", "Win-back (not renewing)"


class CaseReason(models.Model):
    """Configurable reason lists: why a customer is inactive / why they did not renew."""
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.INACTIVITY)
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
    WINBACK = "winback", "Win-back (expired / used up, not renewed)"


class CaseStatus(models.TextChoices):
    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"


class Outcome(models.TextChoices):
    RESOLVED = "resolved", "Resolved"
    STILL_INACTIVE = "still_inactive", "Still inactive"
    LOST = "lost", "Lost"
    WON_BACK = "won_back", "Won back (renewed)"


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
    # win-back: when the service ended, and what came back (approved payments after the case opened)
    ended_at = models.DateTimeField(null=True, blank=True)
    recovered_amount = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "crm_followup_case"
        ordering = ("-opened_at",)
        indexes = [models.Index(fields=["user", "status"]), models.Index(fields=["service", "status"])]


class MessageTemplate(models.Model):
    """Editable message for follow-ups (rendered with {name}, {username}, {service}, {site}, {guide},
    and for win-back also {renew}, {code}, {percent}, {code_expires})."""
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.INACTIVITY)
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
    DISCOUNT = "discount", "Discount code issued"


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


# --- retention (phase 4) ------------------------------------------------------------
class WarningKind(models.TextChoices):
    DATA = "data", "Data used (%)"
    TIME = "time", "Days left"


class WarningRule(models.Model):
    """A pre-expiry warning threshold with its own message (fa / en). Variables:
    {name} {service} {remaining_gb} {remaining_days} {renew}."""
    kind = models.CharField(max_length=4, choices=WarningKind.choices)
    threshold = models.PositiveIntegerField(help_text="percent used (data) or days left (time)")
    is_active = models.BooleanField(default=True)
    title_fa = models.CharField(max_length=120)
    title_en = models.CharField(max_length=120, blank=True, default="")
    body_fa = models.TextField()
    body_en = models.TextField(blank=True, default="")

    class Meta:
        db_table = "crm_warning_rule"
        ordering = ("kind", "-threshold")
        constraints = [models.UniqueConstraint(fields=["kind", "threshold"], name="crm_warning_rule_unique")]


class ServiceWarning(models.Model):
    """One warning for one service period (period_key changes when the service is renewed)
    — the unique constraint makes it impossible to send the same threshold twice. Each
    channel is recorded separately, so a retry only sends the channels still missing;
    bot / email wait for `due_at` during quiet hours."""
    service = models.ForeignKey("panel.Service", on_delete=models.CASCADE, related_name="warnings")
    rule = models.ForeignKey(WarningRule, null=True, on_delete=models.SET_NULL, related_name="sent")
    kind = models.CharField(max_length=4, choices=WarningKind.choices)
    threshold = models.PositiveIntegerField()
    period_key = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    due_at = models.DateTimeField(default=timezone.now)          # bot / email not before this (quiet hours)
    site_sent_at = models.DateTimeField(null=True, blank=True)
    bot_sent_at = models.DateTimeField(null=True, blank=True)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    bot_error = models.CharField(max_length=200, blank=True, default="")
    email_error = models.CharField(max_length=200, blank=True, default="")
    notification = models.ForeignKey("notifications.Notification", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    renewed_at = models.DateTimeField(null=True, blank=True)     # a renewal / new purchase followed within the window

    class Meta:
        db_table = "crm_service_warning"
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(fields=["service", "kind", "threshold", "period_key"], name="crm_service_warning_once")]


class ServiceEndMark(models.Model):
    """When a service was first seen expired / used up (the panel does not say when
    data ran out). Removed once the service is live again."""
    service = models.OneToOneField("panel.Service", on_delete=models.CASCADE, related_name="crm_end")
    status = models.CharField(max_length=10)
    ended_at = models.DateTimeField()

    class Meta:
        db_table = "crm_service_end"


class DiscountKind(models.TextChoices):
    WINBACK = "winback", "Win-back (one customer, one use)"
    CAMPAIGN = "campaign", "Discount code"


class DiscountType(models.TextChoices):
    PERCENT = "percent", "Percent"
    FIXED = "fixed", "Fixed amount"


class DiscountAudience(models.TextChoices):
    ALL = "all", "All customers"
    SELECTED = "selected", "Selected customers"


class DiscountAppliesTo(models.TextChoices):
    NEW = "new", "New purchase"
    RENEW = "renew", "Renewal / top-up"
    BOTH = "both", "Both"


class DiscountCode(models.Model):
    """A discount code (v1.20 win-back, v1.26 "Discount codes" page — one model).

    Rules live in apps/crm/discounts.py (evaluate). A win-back code is a code with
    kind=winback, `user` set (only that customer), percent, one use. Every code is
    applied at order creation, BEFORE the unique amount is added — so the SMS matcher
    and card review always see the final price (Order.amount_unique)."""
    code = models.CharField(max_length=32, unique=True)
    kind = models.CharField(max_length=10, choices=DiscountKind.choices, default=DiscountKind.WINBACK)
    name = models.CharField(max_length=100, blank=True, default="")
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    # win-back owner (the only customer who may use it); null for page codes
    user = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.CASCADE, related_name="discount_codes")
    discount_type = models.CharField(max_length=8, choices=DiscountType.choices, default=DiscountType.PERCENT)
    percent = models.PositiveSmallIntegerField(default=0)
    max_discount = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True,
                                       help_text="cap for a percent code, tomans")
    amount_off = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True,
                                     help_text="fixed discount, tomans")
    audience = models.CharField(max_length=10, choices=DiscountAudience.choices, default=DiscountAudience.ALL)
    customers = models.ManyToManyField("accounts.User", blank=True, related_name="eligible_discount_codes",
                                       db_table="crm_discount_code_customer")
    first_purchase_only = models.BooleanField(default=False)
    plans = models.ManyToManyField("plans.Plan", blank=True, related_name="discount_codes",
                                   db_table="crm_discount_code_plan", help_text="none = every plan")
    applies_to = models.CharField(max_length=6, choices=DiscountAppliesTo.choices, default=DiscountAppliesTo.BOTH)
    max_uses = models.PositiveIntegerField(null=True, blank=True, help_text="total, null = unlimited")
    max_uses_per_customer = models.PositiveIntegerField(null=True, blank=True, default=1, help_text="null = unlimited")
    min_order_amount = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True)
    note = models.CharField(max_length=255, blank=True, default="")
    case = models.ForeignKey(FollowUpCase, null=True, blank=True, on_delete=models.SET_NULL, related_name="discounts")
    # win-back: the order that holds the code (one open invoice per code); used_at when it is paid
    order = models.ForeignKey("orders.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="discount_codes")
    used_at = models.DateTimeField(null=True, blank=True)
    created_by = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "crm_discount_code"
        ordering = ("-created_at",)
