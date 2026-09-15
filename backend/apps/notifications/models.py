from django.db import models


class NotificationType(models.TextChoices):
    BROADCAST = "broadcast", "Broadcast"  # kept for existing rows / apps.notifications.dispatch.broadcast()
    EVENT = "event", "Event"  # kept as the generic default for existing call sites
    ORDER_CONFIRMED = "order_confirmed", "Order confirmed"
    SERVICE_READY = "service_ready", "Service ready"
    VOLUME_WARNING = "volume_warning", "Volume warning"
    EXPIRY_WARNING = "expiry_warning", "Expiry warning"
    ADMIN_BROADCAST = "admin_broadcast", "Admin broadcast"


class Notification(models.Model):
    """data-model · Module 6 · `notification`."""

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
