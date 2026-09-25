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
