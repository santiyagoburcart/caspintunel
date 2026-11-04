from django.db import models
from apps.tenancy.fields import tenant_fk


class NotificationType(models.TextChoices):
    BROADCAST = "broadcast", "Broadcast"  # kept for existing rows / apps.notifications.dispatch.broadcast()
    EVENT = "event", "Event"  # kept as the generic default for existing call sites
    ORDER_CONFIRMED = "order_confirmed", "Order confirmed"
    SERVICE_READY = "service_ready", "Service ready"
    VOLUME_WARNING = "volume_warning", "Volume warning"
    EXPIRY_WARNING = "expiry_warning", "Expiry warning"
    ADMIN_BROADCAST = "admin_broadcast", "Admin broadcast"
    TICKET = "ticket", "Ticket update"


class Notification(models.Model):
    """data-model · Module 6 · `notification`."""

    tenant = tenant_fk()  # multi-tenant, docs/multi-tenant.md (Phase 1)
    type = models.CharField(max_length=20, choices=NotificationType.choices)
    # `title`/`body` are the Persian (default) content — kept unrenamed so every
    # existing notify_user(title=..., body=...) call site keeps working as-is.
    title = models.CharField(max_length=200)
    body = models.TextField()
    title_en = models.CharField(max_length=200, blank=True)
    body_en = models.TextField(blank=True)
    target_user = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.CASCADE,
        related_name="notifications", help_text="null = broadcast",
    )
    # where the bell item leads on the user site (e.g. "/tickets/12"), empty = nowhere
    link = models.CharField(max_length=200, blank=True, default="")
    via_site = models.BooleanField(default=True)
    via_bot = models.BooleanField(default=False)
    via_email = models.BooleanField(default=False)
    created_by_staff = models.ForeignKey(
        "accounts.Staff", null=True, blank=True, on_delete=models.SET_NULL, related_name="notifications"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "notification"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.type}: {self.title}"


class DeliveryChannel(models.TextChoices):
    SITE = "site", "Site"
    BOT = "bot", "Bot"
    EMAIL = "email", "Email"


class DeliveryStatus(models.TextChoices):
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"
    READ = "read", "Read"


class NotificationDelivery(models.Model):
    """data-model · Module 6 · `notification_delivery`."""

    tenant = tenant_fk()  # multi-tenant, docs/multi-tenant.md (Phase 1)
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name="deliveries")
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="notification_deliveries")
    channel = models.CharField(max_length=6, choices=DeliveryChannel.choices)
    status = models.CharField(max_length=6, choices=DeliveryStatus.choices, default=DeliveryStatus.SENT)
    error = models.CharField(max_length=255, blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notification_delivery"
        ordering = ("-sent_at",)
        indexes = [models.Index(fields=["user", "channel", "status"])]

    def __str__(self) -> str:
        return f"delivery#{self.pk} {self.channel} {self.status}"


class PushSubscription(models.Model):
    """v1.33 Web Push: one browser subscription of a customer (user) or a staff member.
    Deleted when the push service answers 404 / 410 (expired)."""

    tenant = tenant_fk()  # multi-tenant, docs/multi-tenant.md (Phase 1)
    endpoint = models.TextField()
    endpoint_hash = models.CharField(max_length=64, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    user = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.CASCADE,
                             related_name="push_subscriptions")
    staff = models.ForeignKey("accounts.Staff", null=True, blank=True, on_delete=models.CASCADE,
                              related_name="push_subscriptions")
    # v1.38.2: an agency reseller (/agency/ portal; not a User / Staff row) — their PasarGuard username
    reseller = models.CharField(max_length=255, blank=True, default="", db_default="", db_index=True)
    user_agent = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    last_ok_at = models.DateTimeField(null=True, blank=True)
    failures = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "push_subscription"

    def __str__(self) -> str:
        return f"push#{self.pk} {'staff' if self.staff_id else 'reseller' if self.reseller else 'user'}"
