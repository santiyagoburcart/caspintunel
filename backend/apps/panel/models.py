from django.conf import settings
from django.db import models

from apps.common.fields import EncryptedTextField
from apps.common.models import TimeStampedModel

from .constants import default_group_ids
from apps.tenancy.fields import tenant_fk


class Panel(TimeStampedModel):
    """A Pasargad / Marzneshin panel we provision users on (data-model · Module 2)."""

    name = models.CharField(max_length=100)
    base_url = models.URLField(help_text="e.g. https://pas.hunaex.shop")
    admin_username = models.CharField(max_length=150)
    admin_password_enc = EncryptedTextField(help_text="stored encrypted at rest")
    token_cache = EncryptedTextField(null=True, blank=True, help_text="cached API token")
    token_expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    # PasarGuard groups (bundles of inbounds) — fallback when a Plan sets no group_ids.
    default_group_ids = models.JSONField(
        default=default_group_ids, blank=True,
        help_text="fallback PasarGuard group id list, e.g. [5, 6, 8, 10]",
    )
    subscription_base_url = models.CharField(
        max_length=255, blank=True,
        help_text="optional; prepended when the API returns a relative subscription_url",
    )
    verify_ssl = models.BooleanField(default=True)

    class Meta:
        db_table = "panel"
        ordering = ("id",)

    def __str__(self) -> str:
        return self.name


class ServiceStatus(models.TextChoices):
    ON_HOLD = "on_hold", "On-Hold"
    ACTIVE = "active", "Active"
    EXPIRED = "expired", "Expired"
    LIMITED = "limited", "Limited"
    DISABLED = "disabled", "Disabled"
    PENDING = "pending", "Pending"


class ExpireStrategy(models.TextChoices):
    FIXED_DATE = "fixed_date", "Fixed date"
    ON_HOLD = "on_hold", "On-Hold (start on first connection)"
    NEVER = "never", "Never (timeless)"


class Service(TimeStampedModel):
    """One VPN account = one username on a panel (data-model · Module 2 · `service`)."""

    tenant = tenant_fk()  # multi-tenant, docs/multi-tenant.md (Phase 1)
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="services")
    panel = models.ForeignKey(Panel, on_delete=models.PROTECT, related_name="services")
    # unique per panel (see Meta) — the same username may exist on another panel
    panel_username = models.CharField(max_length=64)
    subscription_url = models.CharField(max_length=500, blank=True, help_text="fixed — used for QR")

    status = models.CharField(max_length=10, choices=ServiceStatus.choices, default=ServiceStatus.PENDING)
    expire_strategy = models.CharField(
        max_length=12, choices=ExpireStrategy.choices, default=ExpireStrategy.ON_HOLD
    )

    data_limit = models.BigIntegerField(default=0, help_text="bytes; 0 = unlimited")
    data_used = models.BigIntegerField(default=0, help_text="bytes; cached from panel")
    expire_at = models.DateTimeField(null=True, blank=True, help_text="null = timeless")

    on_hold_duration = models.IntegerField(
        null=True, blank=True, help_text="seconds applied after first connection"
    )
    on_hold_timeout = models.DateTimeField(
        null=True, blank=True, help_text="deadline for the first connection"
    )
    online_at = models.DateTimeField(null=True, blank=True, help_text="last seen online (synced)")
    last_synced_at = models.DateTimeField(null=True, blank=True, help_text="last successful panel sync")

    device_limit = models.IntegerField(null=True, blank=True, help_text="null = unlimited")
    current_plan = models.ForeignKey(
        "plans.Plan", null=True, blank=True, on_delete=models.SET_NULL, related_name="services"
    )
    source = models.CharField(max_length=8, default="site")

    alert_vol_sent = models.BooleanField(default=False)
    alert_exp_sent = models.BooleanField(default=False)
    # v1.55: the PasarGuard user has WireGuard peers (any plan / group, mirrored by every sync — panel/wireguard.py)
    wireguard = models.BooleanField(default=False)

    class Meta:
        db_table = "service"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["panel", "panel_username"], name="uniq_service_panel_username"
            ),
        ]

    def __str__(self) -> str:
        return self.panel_username


class WireguardLocation(models.Model):
    """v1.55 «مکان‌های وایرگارد»: the country name + flag of a WireGuard location, matched by the code in its PasarGuard host
    remark («Ita {USERNAME}» → Ita). Editable by our staff; an unknown code shows as itself. Platform table (shared)."""

    code = models.CharField(max_length=40, unique=True, help_text="the host remark's code, e.g. Ita, de, IR (case-insensitive)")
    name_fa = models.CharField(max_length=60)
    name_en = models.CharField(max_length=60)
    flag = models.CharField(max_length=16, blank=True, default="")
    slug = models.CharField(max_length=24, blank=True, default="", help_text="file name part, e.g. germany")
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "wireguard_location"
        ordering = ("sort_order", "name_en")

    def __str__(self) -> str:
        return f"{self.flag} {self.name_en}".strip()


def shows_subscription(service) -> bool:
    """v1.55: a «فقط وایرگارد» plan shows no subscription link anywhere (site, Mini App, bot, delivery message, QR)."""
    plan = getattr(service, "current_plan", None)
    return not (plan is not None and getattr(plan, "vpn_type", "sub") == "wireguard")


def customer_sub_url(service) -> str:
    return (service.subscription_url or "") if shows_subscription(service) else ""

