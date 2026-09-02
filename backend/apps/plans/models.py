from django.db import models

from apps.common.models import TimeStampedModel


class PlanType(models.TextChoices):
    FIXED = "fixed", "Fixed"
    CUSTOM_VOLUME = "custom_volume", "Custom volume"


class Plan(TimeStampedModel):
    """Sales plan — independent of panel user_templates (data-model · Module 3)."""

    name_fa = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120, blank=True)
    desc_fa = models.TextField(blank=True)
    desc_en = models.TextField(blank=True)

    type = models.CharField(max_length=13, choices=PlanType.choices, default=PlanType.FIXED)

    data_limit = models.BigIntegerField(null=True, blank=True, help_text="bytes; null = unlimited")
    duration_days = models.IntegerField(null=True, blank=True, help_text="null = timeless")
    device_limit = models.IntegerField(null=True, blank=True, help_text="null = unlimited")

    price = models.DecimalField(max_digits=12, decimal_places=0, help_text="tomans")
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    # Panel groups this plan's service attaches to. Empty (the default) -> fall
    # back to Panel.default_group_ids, so unchecking a group at the panel level
    # takes effect for every plan that hasn't deliberately overridden the set.
    group_ids = models.JSONField(
        default=list, blank=True,
        help_text="panel group ids for this plan; empty = use the panel's default set",
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
