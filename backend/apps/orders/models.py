from django.db import models

from apps.common.models import TimeStampedModel


class OrderType(models.TextChoices):
    NEW = "new", "New service"
    RENEW = "renew", "Renew"
    ADDON_VOLUME = "addon_volume", "Add-on volume"
    MANUAL = "manual", "Manual (admin-created)"
    IMPORTED = "imported", "Imported (existing panel account linked)"


class OrderStatus(models.TextChoices):
    PENDING_PAYMENT = "pending_payment", "Pending payment"
    PAID = "paid", "Paid"
    COMPLETED = "completed", "Completed"
    REJECTED = "rejected", "Rejected"
    FAILED = "failed", "Failed"
    EXPIRED = "expired", "Reservation expired"
    # its payment was deleted (voided) by a Super Admin with "cancel the order" (v1.25)
    CANCELLED = "cancelled", "Cancelled"


# Statuses during which the unique amount is reserved and must stay globally unique.
ACTIVE_UNIQUE_STATUSES = (OrderStatus.PENDING_PAYMENT, OrderStatus.PAID)


class Order(TimeStampedModel):
    """Purchase intent (data-model · Module 4 · `order`)."""

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="orders")
    service = models.ForeignKey(
        "panel.Service", null=True, blank=True, on_delete=models.SET_NULL, related_name="orders"
    )
    # null only for `imported` orders — an existing panel account linked by an
    # admin without choosing a plan
    plan = models.ForeignKey(
        "plans.Plan", null=True, blank=True, on_delete=models.PROTECT, related_name="orders"
    )

    type = models.CharField(max_length=12, choices=OrderType.choices, default=OrderType.NEW)
    requested_account_name = models.CharField(max_length=64, null=True, blank=True)
    custom_volume_gb = models.IntegerField(null=True, blank=True)

    amount = models.DecimalField(max_digits=12, decimal_places=0, help_text="base amount, tomans")
    # discount code (apps.crm.DiscountCode — win-back or a "Discount codes" page code)
    # already taken off `amount`: original_amount − discount_amount = amount (the final
    # price; amount_unique = amount + surcharge is what the customer pays). 0 = none.
    discount_amount = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    original_amount = models.DecimalField(max_digits=12, decimal_places=0, default=0,
                                          help_text="price before the discount code, tomans (v1.26)")
    discount_code = models.ForeignKey("crm.DiscountCode", null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name="orders")
    discount_code_text = models.CharField(max_length=32, blank=True, default="", help_text="code as typed, kept if deleted")
    amount_unique = models.DecimalField(
        max_digits=12, decimal_places=0, help_text="amount + unique surcharge (200..1500)"
    )
    # Faithful implementation of the data-model 'partial unique on active amount_unique':
    # MySQL has no partial indexes, so we mirror amount_unique here only while the
    # reservation is active and NULL it out otherwise (MySQL allows many NULLs in a
    # UNIQUE column). Managed by the allocation logic in the orders phase.
    amount_unique_lock = models.DecimalField(
        max_digits=12, decimal_places=0, null=True, blank=True, unique=True, editable=False
    )
    unique_expire_at = models.DateTimeField(help_text="reservation expiry")

    status = models.CharField(
        max_length=16, choices=OrderStatus.choices, default=OrderStatus.PENDING_PAYMENT, db_index=True
    )
    source = models.CharField(max_length=8, default="site")
    # paid, but the chosen account name turned out to exist on the panel (someone
    # else's account): never attached — the customer picks another name (site / bot)
    needs_new_name = models.BooleanField(default=False)
    # v1.38 «فاکتور دستی»: the staff invoice this order belongs to (tag «دستی» everywhere)
    manual_invoice = models.ForeignKey("orders.ManualInvoice", null=True, blank=True, on_delete=models.SET_NULL,
                                       related_name="orders")

    class Meta:
        db_table = "order"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["amount_unique", "status"])]

    def __str__(self) -> str:
        return f"order#{self.pk} {self.type} {self.status}"

    def sync_unique_lock(self):
        """Keep amount_unique_lock in step with status; call before save in logic layer."""
        self.amount_unique_lock = self.amount_unique if self.status in ACTIVE_UNIQUE_STATUSES else None


class ScheduledRenewal(TimeStampedModel):
    """A paid renewal waiting for its service to actually reach the end of its
    current cycle (expired or out of volume) before the new plan is applied —
    see apps.panel.services.apply_scheduled_renewal and the periodic task in
    apps.panel.tasks.apply_due_scheduled_renewals."""

    service = models.OneToOneField(
        "panel.Service", on_delete=models.CASCADE, related_name="scheduled_renewal"
    )
    plan = models.ForeignKey("plans.Plan", on_delete=models.PROTECT, related_name="scheduled_renewals")
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="scheduled_renewals")

    # copied from the plan at purchase time so a later plan edit never changes
    # how an already-paid renewal gets applied
    renewal_mode = models.CharField(max_length=10)
    carry_over_data = models.CharField(max_length=11, null=True, blank=True)

    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "scheduled_renewal"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"scheduled_renewal#{self.pk} for service#{self.service_id}"


class ManualInvoice(TimeStampedModel):
    """v1.38 «فاکتور دستی» created by staff from a customer's profile (apps/orders/manual.py).
    mode "paid"   = «قبلاً پرداخت شده»: an approved payment + completed order, on the entered payment date.
    mode "issued" = «صدور فاکتور برای پرداخت»: the customer pays it in their panel (normal checkout)."""

    MODE_PAID, MODE_ISSUED = "paid", "issued"
    MODES = [(MODE_PAID, "Already paid"), (MODE_ISSUED, "Issued for payment")]
    OPEN, PAID, CANCELLED = "open", "paid", "cancelled"
    STATUSES = [(OPEN, "Open"), (PAID, "Paid"), (CANCELLED, "Cancelled")]
    ACT_NONE, ACT_NEW, ACT_RENEW, ACT_ADDON = "none", "new", "renew", "addon"
    ACTIONS = [(ACT_NONE, "No service change"), (ACT_NEW, "New service"), (ACT_RENEW, "Renew a service"),
               (ACT_ADDON, "Add volume to a service")]

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="manual_invoices")
    mode = models.CharField(max_length=8, choices=MODES)
    status = models.CharField(max_length=10, choices=STATUSES, default=OPEN, db_index=True)
    plan = models.ForeignKey("plans.Plan", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    title = models.CharField(max_length=120, blank=True, default="")
    volume_gb = models.PositiveIntegerField(null=True, blank=True)
    days = models.PositiveIntegerField(null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=0, help_text="tomans")
    service_action = models.CharField(max_length=6, choices=ACTIONS, default=ACT_NONE)
    service = models.ForeignKey("panel.Service", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    account_name = models.CharField(max_length=64, blank=True, default="")
    due_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True, default="")
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                              help_text="the order that paid it")
    created_by = models.ForeignKey("accounts.Staff", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        db_table = "manual_invoice"
        ordering = ("-created_at",)

    @property
    def number(self) -> str:
        return f"MI-{int(self.pk):06d}" if self.pk else ""

    def label(self, lang: str = "fa") -> str:
        if self.title:
            return self.title
        if self.plan_id:
            return (self.plan.name_en if lang == "en" else self.plan.name_fa) or self.plan.name_fa
        return self.number
