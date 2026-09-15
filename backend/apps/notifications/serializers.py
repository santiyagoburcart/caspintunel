from rest_framework import serializers

from .models import DeliveryStatus, NotificationDelivery


class NotificationDeliverySerializer(serializers.ModelSerializer):
    """A user's-eye view of one delivered notification (site channel)."""

    type = serializers.CharField(source="notification.type", read_only=True)
    title = serializers.CharField(source="notification.title", read_only=True)
    title_en = serializers.CharField(source="notification.title_en", read_only=True)
    body = serializers.CharField(source="notification.body", read_only=True)
    body_en = serializers.CharField(source="notification.body_en", read_only=True)
    created_at = serializers.DateTimeField(source="notification.created_at", read_only=True)
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = NotificationDelivery
        fields = ("id", "type", "title", "title_en", "body", "body_en", "created_at", "is_read")

    def get_is_read(self, obj) -> bool:
        return obj.status == DeliveryStatus.READ
