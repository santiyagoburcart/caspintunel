from rest_framework import serializers

from .models import BankCard, Payment


class BankCardSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankCard
        fields = ("id", "card_number", "holder_name", "bank_name")


class PaymentSerializer(serializers.ModelSerializer):
    order_id = serializers.IntegerField(source="order.id", read_only=True)
    user = serializers.CharField(source="order.user.username", read_only=True)
    receipt_url = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = (
            "id", "order_id", "user", "method", "amount", "status",
            "receipt_url", "bank_card", "confirmed_by", "confirmed_at",
            "reject_reason", "created_at",
        )
        read_only_fields = fields

    def get_receipt_url(self, obj) -> str | None:
        """Authenticated endpoint, not a public media path — see ReceiptFileView."""
        if not obj.receipt_image:
            return None
        return f"/api/v1/payments/{obj.id}/receipt/"


class ReceiptUploadSerializer(serializers.Serializer):
    order = serializers.IntegerField()
    receipt_image = serializers.ImageField()
    bank_card = serializers.PrimaryKeyRelatedField(
        queryset=BankCard.objects.filter(is_active=True), required=False, allow_null=True
    )


class RejectSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class SmsInboundSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=2000, trim_whitespace=False)
    sender = serializers.CharField(max_length=32, required=False, allow_blank=True)
    received_at = serializers.DateTimeField(required=False)
