from rest_framework import serializers

from .models import Plan, PlanType


class PlanPanelDefaultMixin:
    """MP-Phase 1 backward-compat: `panel` is a required FK on the model, but the
    admin UI hasn't grown a panel picker yet. When it's omitted and the install
    has exactly one panel, use it; with several panels the caller must choose.
    """

    def validate_panel(self, value):
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if not attrs.get("panel") and (self.instance is None or self.instance.panel_id is None):
            from apps.panel.models import Panel

            panels = list(Panel.objects.order_by("id")[:2])
            if len(panels) == 1:
                attrs["panel"] = panels[0]
            elif not panels:
                raise serializers.ValidationError({"panel": "no panel configured"})
            else:
                raise serializers.ValidationError(
                    {"panel": "required — this install has multiple panels"}
                )
        return attrs


class PlanSerializer(serializers.ModelSerializer):
    """Customer-facing representation."""

    final_price = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields = (
            "id", "type", "name_fa", "name_en", "desc_fa", "desc_en",
            "category_fa", "category_en",
            "data_limit", "duration_days", "device_limit",
            "price", "discount_percent", "final_price",
            "min_gb", "max_gb", "price_per_gb", "sort_order",
        )

    def get_final_price(self, obj) -> str | None:
        if obj.type == PlanType.CUSTOM_VOLUME:
            return None
        return str(obj.final_price)


class PlanWriteSerializer(PlanPanelDefaultMixin, serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = (
            "id", "type", "name_fa", "name_en", "desc_fa", "desc_en",
            "panel", "category_fa", "category_en",
            "data_limit", "duration_days", "device_limit",
            "price", "discount_percent", "is_active", "sort_order",
            "min_gb", "max_gb", "price_per_gb", "group_ids",
        )
        extra_kwargs = {"panel": {"required": False}}

    def validate(self, attrs):
        merged = {**getattr(self.instance, "__dict__", {}), **attrs}
        if merged.get("type") == PlanType.CUSTOM_VOLUME:
            if merged.get("price_per_gb") is None:
                raise serializers.ValidationError("custom-volume plans need price_per_gb")
            if not merged.get("max_gb"):
                raise serializers.ValidationError("custom-volume plans need max_gb")
        return super().validate(attrs)

    def validate_group_ids(self, value):
        return [int(x) for x in (value or [])]
