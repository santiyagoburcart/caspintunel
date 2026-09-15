from django.db import models

from apps.common.models import TimeStampedModel


class PlanType(models.TextChoices):
    FIXED = "fixed", "Fixed"
    CUSTOM_VOLUME = "custom_volume", "Custom volume"


class RenewalMode(models.TextChoices):
    RESET = "reset", "Reset (mode A)"
    CARRY_OVER = "carry_over", "Carry over (mode B)"


class CarryOverData(models.TextChoices):
    BOTH = "both", "Time + volume"
    TIME_ONLY = "time_only", "Time only"
    VOLUME_ONLY = "volume_only", "Volume only"


class Plan(TimeStampedModel):
    """Sales plan — independent of panel user_templates (data-model · Module 3)."""

    name_fa = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120, blank=True)
    desc_fa = models.TextField(blank=True)
    desc_en = models.TextField(blank=True)

    # Multi-panel: every plan is provisioned on exactly one panel. The plan's
    # service always lives on this panel; its group_ids are scoped to it.
    panel = models.ForeignKey(
        "panel.Panel", on_delete=models.PROTECT, related_name="plans",
        help_text="the panel this plan's services are created / renewed on",
    )

    # Optional grouping for the store / bot (e.g. wireguard, unlimited, volume).
    # Free-text bilingual labels — grouping later matches on these.
    category_fa = models.CharField(max_length=60, blank=True)
    category_en = models.CharField(max_length=60, blank=True)

    type = models.CharField(max_length=13, choices=PlanType.choices, default=PlanType.FIXED)

    data_limit = models.BigIntegerField(null=True, blank=True, help_text="bytes; null = unlimited")
    duration_days = models.IntegerField(null=True, blank=True, help_text="null = timeless")
    device_limit = models.IntegerField(null=True, blank=True, help_text="null = unlimited")

    price = models.DecimalField(max_digits=12, decimal_places=0, help_text="tomans")
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    # what happens to a service's leftover time/volume when this plan renews it —
    # see apps.panel.services.apply_scheduled_renewal for the actual application
    renewal_mode = models.CharField(max_length=10, choices=RenewalMode.choices, default=RenewalMode.RESET)
    carry_over_data = models.CharField(
        max_length=11, choices=CarryOverData.choices, null=True, blank=True,
        help_text="only meaningful when renewal_mode=carry_over",
    )

    # Panel groups this plan's service attaches to — scoped to `self.panel`.
    # Empty (the default) -> fall back to that panel's default_group_ids, so
    # unchecking a group at the panel level takes effect for every plan that
    # hasn't deliberately overridden the set.
    group_ids = models.JSONField(
        default=list, blank=True,
        help_text="panel group ids for this plan (from its own panel); empty = the panel's default set",
    )

    # custom_volume only
    min_gb = models.IntegerField(null=True, blank=True)
    max_gb = models.IntegerField(null=True, blank=True)
    price_per_gb = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True)

    class Meta:
        db_table = "plan"
        ordering = ("sort_order", "id")

    def __str__(self) -> str:
        return self.name_fa or self.name_en or f"plan#{self.pk}"

    @property
    def final_price(self):
        return self._apply_discount(self.price)

    def _apply_discount(self, amount):
        from decimal import ROUND_HALF_UP, Decimal

        net = Decimal(amount) - (Decimal(amount) * self.discount_percent / Decimal(100))
        return net.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    def price_for_volume(self, gb: int):
        """Custom-volume plan: total price for `gb` gigabytes (discount applied)."""
        from decimal import Decimal

        if self.type != PlanType.CUSTOM_VOLUME or self.price_per_gb is None:
            raise ValueError("plan is not a custom-volume plan")
        base = self.price + (Decimal(self.price_per_gb) * Decimal(int(gb)))
        return self._apply_discount(base)

    def data_limit_for_volume(self, gb: int) -> int:
        return int(gb) * 1024**3
