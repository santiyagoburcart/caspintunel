from django.db import models

from apps.common.models import TimeStampedModel


class OrderType(models.TextChoices):
    NEW = "new", "New service"
    RENEW = "renew", "Renew"
    ADDON_VOLUME = "addon_volume", "Add-on volume"


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
    plan = models.ForeignKey("plans.Plan", on_delete=models.PROTECT, related_name="orders")

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
