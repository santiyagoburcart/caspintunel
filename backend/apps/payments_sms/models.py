import secrets

from django.db import models
from django.utils import timezone

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
class AmountUnit(models.TextChoices):
    RIAL = "rial", "Rial"
    TOMAN = "toman", "Toman"


class SmsSource(models.Model):
    phone_number = models.CharField(max_length=20)
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    # unit of the amounts in this bank's SMS — used ONLY when the SMS itself
    # names no unit (ریال / تومان); never a guess, never both
    amount_unit = models.CharField(max_length=5, choices=AmountUnit.choices, default=AmountUnit.RIAL,
                                   db_default=AmountUnit.RIAL)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

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
    # what the device said the sender was (also kept when it is not an allowed source)
    sender = models.CharField(max_length=64, blank=True, default="")
    # deposit in WHOLE tomans (null when there is none, or a rial amount is not a
    # multiple of 10); parsed_raw/parsed_unit = the number as written + its unit
    parsed_amount = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True)
    parsed_raw = models.BigIntegerField(null=True, blank=True)
    parsed_unit = models.CharField(max_length=5, blank=True, default="", db_default="")
    matched_order = models.ForeignKey(
        "orders.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="sms_messages"
    )
    # a deposit close to (but not exactly) an open invoice: never approved, linked
    # here for manual review — kind "less" / "more" than the invoice
    mismatch_order = models.ForeignKey(
        "orders.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="sms_mismatches"
    )
    mismatch_kind = models.CharField(max_length=4, blank=True, default="", db_default="")
    # why it matched / did not match — shown in the admin SMS log
    note = models.CharField(max_length=255, blank=True, default="")
    # when the phone got the SMS (device time, if it said so) vs when it reached us —
    # an offline queue (iPhone Shortcut batch) can deliver it hours later
    received_at = models.DateTimeField(default=timezone.now)
    uploaded_at = models.DateTimeField(default=timezone.now)
    # batch uploads: sha256(device | text | received_at) — the same SMS is stored (and matched) once
    dedupe_key = models.CharField(max_length=64, null=True, blank=True, unique=True)

    LATE_AFTER_SECONDS = 120

    @property
    def delivered_late(self) -> bool:
        return bool(self.received_at and self.uploaded_at
                    and (self.uploaded_at - self.received_at).total_seconds() > self.LATE_AFTER_SECONDS)

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
    SMS_MISMATCH = "sms_mismatch", "SMS — amount mismatch (manual review)"
    GATEWAY = "gateway", "Gateway"


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class ConfirmedBy(models.TextChoices):
    ADMIN = "admin", "Admin"
    SYSTEM = "system", "System"


class VoidServiceAction(models.TextChoices):
    """What a Super Admin chose for the linked order / service when deleting (voiding) a payment."""
    KEEP = "keep", "Keep the order and service"
    DISABLE = "disable", "Cancel the order, disable the service on PasarGuard"
    DELETE = "delete", "Cancel the order, delete the service on PasarGuard"


TX_PREFIX = "TX-"


def format_tx(number) -> str:
    return f"{TX_PREFIX}{int(number):06d}" if number else ""


class PaymentQuerySet(models.QuerySet):
    def live(self):
        """Not deleted (voided) by a Super Admin — the only rows that count anywhere
        (totals, Accounting, Analytics, reports, review queue)."""
        return self.filter(voided_at__isnull=True)


class Payment(TimeStampedModel):
    objects = PaymentQuerySet.as_manager()

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
    # v1.30.1 duplicate-receipt checks (apps/payments_sms/checks.py): sha256 of the image
    # bytes (set on upload), and what the receipt says — bank document / tracking number
    # (digits only) and amount in tomans — typed by the customer (optional) or by staff
    receipt_sha256 = models.CharField(max_length=64, blank=True, default="", db_index=True)
    receipt_ref = models.CharField(max_length=40, blank=True, default="", db_index=True)
    receipt_amount = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True)
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
    # human-readable transaction number (TX-000123): sequential and unique — the row's
    # own id, written right after the insert (save) and backfilled for older rows
    number = models.PositiveIntegerField(null=True, blank=True, unique=True, editable=False)
    # Super Admin "delete" = void (apps/payments_sms/voiding.py): hidden from lists and
    # every total; restorable for VOID_RESTORE_DAYS. Never a hard delete.
    voided_at = models.DateTimeField(null=True, blank=True, db_index=True)
    voided_by = models.ForeignKey("accounts.Staff", null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="voided_payments")
    void_reason = models.CharField(max_length=255, blank=True, default="")
    void_service_action = models.CharField(max_length=8, choices=VoidServiceAction.choices, blank=True, default="")
    # the order status before the void (cancel) — put back by a restore
    void_prev_order_status = models.CharField(max_length=16, blank=True, default="")

    class Meta:
        db_table = "payment"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"payment#{self.pk} {self.method} {self.status}"

    @property
    def tx_number(self) -> str:
        return format_tx(self.number or self.pk)

    @property
    def is_voided(self) -> bool:
        return self.voided_at is not None

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.number is None and self.pk:
            self.number = self.pk
            type(self).objects.filter(pk=self.pk, number__isnull=True).update(number=self.pk)
