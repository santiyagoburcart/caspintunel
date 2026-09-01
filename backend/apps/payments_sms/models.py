import secrets

from django.db import models

from apps.common.models import TimeStampedModel


# ---------------------------------------------------------------------------
# Bank cards (data-model · Module 4 · `bank_card`)
# ---------------------------------------------------------------------------
class BankCard(models.Model):
    card_number = models.CharField(max_length=20)
    holder_name = models.CharField(max_length=120)
    bank_name = models.CharField(max_length=80, blank=True)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "bank_card"
        ordering = ("sort_order", "id")

    def __str__(self) -> str:
        return f"{self.bank_name} {self.card_number}".strip()


# ---------------------------------------------------------------------------
# SMS confirmation (data-model · Module 5)
# ---------------------------------------------------------------------------
class SmsSource(models.Model):
    phone_number = models.CharField(max_length=20)
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "sms_source"
        ordering = ("id",)

    def __str__(self) -> str:
        return self.phone_number


def generate_device_token() -> str:
    return secrets.token_urlsafe(32)


class SmsAppDevice(models.Model):
    name = models.CharField(max_length=100)
    api_token = models.CharField(max_length=64, unique=True, default=generate_device_token)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sms_app_device"
        ordering = ("id",)

    def __str__(self) -> str:
        return self.name


class SmsMessage(models.Model):
    sms_source = models.ForeignKey(
        SmsSource, null=True, blank=True, on_delete=models.SET_NULL, related_name="messages"
    )
    device = models.ForeignKey(
        SmsAppDevice, null=True, blank=True, on_delete=models.SET_NULL, related_name="messages"
    )
    raw_text = models.TextField()
    parsed_amount = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True)
    matched_order = models.ForeignKey(
        "orders.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="sms_messages"
    )
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sms_message"
        ordering = ("-received_at",)

    def __str__(self) -> str:
        return f"sms#{self.pk} {self.parsed_amount or '?'}"


# ---------------------------------------------------------------------------
# Payments (data-model · Module 4 · `payment`)
# ---------------------------------------------------------------------------
class PaymentMethod(models.TextChoices):
    CARD_MANUAL = "card_manual", "Card-to-card (manual)"
    SMS_AUTO = "sms_auto", "SMS auto-match"
    GATEWAY = "gateway", "Gateway"


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class ConfirmedBy(models.TextChoices):
    ADMIN = "admin", "Admin"
    SYSTEM = "system", "System"


class Payment(TimeStampedModel):
    order = models.OneToOneField("orders.Order", on_delete=models.CASCADE, related_name="payment")
    bank_card = models.ForeignKey(
        BankCard, null=True, blank=True, on_delete=models.SET_NULL, related_name="payments"
    )
    method = models.CharField(max_length=12, choices=PaymentMethod.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=0)
    status = models.CharField(
        max_length=8, choices=PaymentStatus.choices, default=PaymentStatus.PENDING, db_index=True
    )
    receipt_image = models.ImageField(upload_to="receipts/%Y/%m/", null=True, blank=True)
    sms_message = models.ForeignKey(
        SmsMessage, null=True, blank=True, on_delete=models.SET_NULL, related_name="payments"
    )
    gateway_ref = models.CharField(max_length=128, null=True, blank=True)
    confirmed_by = models.CharField(max_length=8, choices=ConfirmedBy.choices, null=True, blank=True)
    confirmed_by_staff = models.ForeignKey(
        "accounts.Staff", null=True, blank=True, on_delete=models.SET_NULL, related_name="confirmed_payments"
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    reject_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "payment"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"payment#{self.pk} {self.method} {self.status}"
