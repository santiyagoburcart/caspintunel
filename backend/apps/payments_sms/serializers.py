from rest_framework import serializers

from .models import BankCard, Payment


class BankCardSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankCard
        fields = ("id", "card_number", "holder_name", "bank_name")


class PaymentSerializer(serializers.ModelSerializer):
    order_id = serializers.IntegerField(source="order.id", read_only=True)
    user = serializers.CharField(source="order.user.username", read_only=True)

    class Meta:
        model = Payment
        fields = (
            "id", "order_id", "user", "method", "amount", "status",
            "receipt_image", "bank_card", "confirmed_by", "confirmed_at",
            "reject_reason", "created_at",
        )
        read_only_fields = fields


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
