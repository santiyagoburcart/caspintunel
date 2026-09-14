from django.utils import timezone
from rest_framework import serializers

from .models import Service


class ServiceSerializer(serializers.ModelSerializer):
    days_left = serializers.SerializerMethodField()
    data_left = serializers.SerializerMethodField()
    qr = serializers.SerializerMethodField()
    waiting_for_connection = serializers.SerializerMethodField()
    validity_days = serializers.SerializerMethodField()
    plan_name = serializers.CharField(source="current_plan.name_fa", read_only=True, default=None)

    class Meta:
        model = Service
        fields = (
            "id", "panel_username", "subscription_url", "qr", "status",
            "expire_strategy", "data_limit", "data_used", "data_left",
            "expire_at", "days_left", "on_hold_duration", "on_hold_timeout",
            "online_at", "device_limit", "current_plan", "plan_name",
            "waiting_for_connection", "validity_days", "last_synced_at", "created_at",
        )
        read_only_fields = fields

    def get_waiting_for_connection(self, obj) -> bool:
        # on-hold and never connected -> the clock hasn't started yet
        return obj.status == "on_hold" and not obj.online_at

    def get_validity_days(self, obj) -> int | None:
        # how long the plan runs *once activated* (for the on-hold message).
        # Prefer the panel-synced figure; fall back to the plan's own
        # duration_days so the message is correct even before the first sync
        # (or if the panel never reports on_hold_expire_duration at all).
        if obj.on_hold_duration:
            return max(round(obj.on_hold_duration / 86400), 0)
        if obj.current_plan_id and obj.current_plan.duration_days:
            return obj.current_plan.duration_days
        return None

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
