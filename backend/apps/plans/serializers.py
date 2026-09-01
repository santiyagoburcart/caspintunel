from rest_framework import serializers

from .models import Plan, PlanType


class PlanSerializer(serializers.ModelSerializer):
    """Customer-facing representation."""

    final_price = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields = (
            "id", "type", "name_fa", "name_en", "desc_fa", "desc_en",
            "data_limit", "duration_days", "device_limit",
            "price", "discount_percent", "final_price",
            "min_gb", "max_gb", "price_per_gb", "sort_order",
        )

    def get_final_price(self, obj) -> str | None:
        if obj.type == PlanType.CUSTOM_VOLUME:
            return None
        return str(obj.final_price)


class PlanWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = (
            "id", "type", "name_fa", "name_en", "desc_fa", "desc_en",
            "data_limit", "duration_days", "device_limit",
            "price", "discount_percent", "is_active", "sort_order",
            "min_gb", "max_gb", "price_per_gb", "group_ids",
        )

    def validate(self, attrs):
        merged = {**getattr(self.instance, "__dict__", {}), **attrs}
        if merged.get("type") == PlanType.CUSTOM_VOLUME:
            if merged.get("price_per_gb") is None:
                raise serializers.ValidationError("custom-volume plans need price_per_gb")
            if not merged.get("max_gb"):
                raise serializers.ValidationError("custom-volume plans need max_gb")
        return attrs
