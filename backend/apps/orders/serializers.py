from rest_framework import serializers

from apps.plans.models import Plan

from .models import Order, OrderType
from .services import OrderError, create_order


class OrderSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name_fa", read_only=True)
    plan_name_en = serializers.CharField(source="plan.name_en", read_only=True, default="")
    payment_status = serializers.SerializerMethodField()
    payment_method = serializers.SerializerMethodField()
    receipt_url = serializers.SerializerMethodField()
    reject_reason = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id", "type", "status", "plan", "plan_name", "plan_name_en", "service",
            "requested_account_name", "custom_volume_gb",
            "amount", "amount_unique", "unique_expire_at",
            "payment_status", "payment_method", "receipt_url",
            "reject_reason", "source", "created_at",
        )
        read_only_fields = fields

    def get_payment_status(self, obj) -> str | None:
        pay = getattr(obj, "payment", None)
        return pay.status if pay else None

    def get_payment_method(self, obj) -> str | None:
        pay = getattr(obj, "payment", None)
        return pay.method if pay else None

    def get_receipt_url(self, obj) -> str | None:
        # owner-checked endpoint (ReceiptFileView), never a public media path
        pay = getattr(obj, "payment", None)
        return f"/api/v1/payments/{pay.id}/receipt/" if pay and pay.receipt_image else None

    def get_reject_reason(self, obj) -> str:
        pay = getattr(obj, "payment", None)
        return pay.reject_reason if pay and pay.status == "rejected" else ""


class OrderCreateSerializer(serializers.Serializer):
    plan = serializers.PrimaryKeyRelatedField(queryset=Plan.objects.filter(is_active=True))
    type = serializers.ChoiceField(choices=OrderType.choices, default=OrderType.NEW)
    requested_account_name = serializers.RegexField(r"^[A-Za-z0-9_.\-]{2,64}$", required=False, allow_blank=True)
    custom_volume_gb = serializers.IntegerField(required=False, min_value=1)
    service = serializers.IntegerField(required=False)
    # accepted once at sign-up (User.terms_accepted_at); kept only so older
    # clients that still send it don't break
    terms_accepted = serializers.BooleanField(write_only=True, required=False)

    def validate_requested_account_name(self, value):
        from apps.panel.models import Service

        if value and Service.objects.filter(panel_username__iexact=value).exists():
            raise serializers.ValidationError("that account name is taken")
        return value

    def create(self, validated):
        request = self.context["request"]
        try:
            return create_order(
                user=request.user,
                plan_id=validated["plan"].id,
                order_type=validated["type"],
                requested_account_name=validated.get("requested_account_name"),
                custom_volume_gb=validated.get("custom_volume_gb"),
                service_id=validated.get("service"),
                source=self.context.get("source", "site"),
            )
        except OrderError as exc:
            raise serializers.ValidationError(str(exc))
