from django.utils import timezone
from rest_framework import serializers

from .models import Service


class ServiceSerializer(serializers.ModelSerializer):
    days_left = serializers.SerializerMethodField()
    data_left = serializers.SerializerMethodField()
    qr = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = (
            "id", "panel_username", "subscription_url", "qr", "status",
            "expire_strategy", "data_limit", "data_used", "data_left",
            "expire_at", "days_left", "on_hold_timeout", "online_at",
            "device_limit", "current_plan", "created_at",
        )
        read_only_fields = fields

    def get_days_left(self, obj) -> int | None:
        if not obj.expire_at:
            return None
        import math

        seconds = (obj.expire_at - timezone.now()).total_seconds()
        return max(math.ceil(seconds / 86400), 0)

    def get_data_left(self, obj) -> int | None:
        if not obj.data_limit:
            return None  # unlimited
        return max(obj.data_limit - obj.data_used, 0)

    def get_qr(self, obj) -> str | None:
        if not obj.subscription_url:
            return None
        request = self.context.get("request")
        path = f"/api/v1/services/{obj.id}/qr/"
        return request.build_absolute_uri(path) if request else path
