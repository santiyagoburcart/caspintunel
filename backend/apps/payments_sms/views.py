from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.models import Order

from .authentication import IsSmsDevice, SmsDeviceAuthentication
from .matching import ingest_sms
from .models import BankCard, Payment, PaymentStatus
from .serializers import (
    BankCardSerializer,
    PaymentSerializer,
    ReceiptUploadSerializer,
    RejectSerializer,
    SmsInboundSerializer,
)
from .services import PaymentError, approve_payment, reject_payment, submit_receipt


class BankCardListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BankCardSerializer

    def get_queryset(self):
        return BankCard.objects.filter(is_active=True).order_by("sort_order", "id")


class ReceiptUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    throttle_scope = "receipt"

    @extend_schema(request=ReceiptUploadSerializer, responses=PaymentSerializer,
                   summary="Upload a card-to-card receipt (flowchart 1.3)")
    def post(self, request):
        ser = ReceiptUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        order = get_object_or_404(Order, pk=ser.validated_data["order"])
        try:
            payment = submit_receipt(
                order=order,
                image=ser.validated_data["receipt_image"],
                bank_card=ser.validated_data.get("bank_card"),
                user=request.user,
            )
        except PaymentError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(PaymentSerializer(payment).data, status=201)


class PaymentPendingListView(generics.ListAPIView):
    """Admin approval queue."""

    permission_classes = [permissions.IsAdminUser]
    serializer_class = PaymentSerializer

    def get_queryset(self):
        return (
            Payment.objects.filter(status=PaymentStatus.PENDING)
            .select_related("order", "order__user", "bank_card")
            .order_by("created_at")
        )


class PaymentApproveView(APIView):
    permission_classes = [permissions.IsAdminUser]

    @extend_schema(request=None, responses=PaymentSerializer, summary="Approve a pending payment")
    def post(self, request, pk):
        try:
            payment = approve_payment(pk, actor=request.user)
        except PaymentError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(PaymentSerializer(payment).data)


class PaymentRejectView(APIView):
    permission_classes = [permissions.IsAdminUser]

    @extend_schema(request=RejectSerializer, responses=PaymentSerializer, summary="Reject a pending payment")
    def post(self, request, pk):
        ser = RejectSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            payment = reject_payment(pk, reason=ser.validated_data["reason"], actor=request.user)
        except PaymentError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(PaymentSerializer(payment).data)


# --- SMS auto-confirm (Android app; flowchart 1.4) ---------------------
class SmsInboundView(APIView):
    authentication_classes = [SmsDeviceAuthentication]
    permission_classes = [IsSmsDevice]
    throttle_scope = "sms_ingest"

    @extend_schema(request=SmsInboundSerializer, responses=dict,
                   summary="Ingest one deposit SMS and try to auto-confirm an order")
    def post(self, request):
        ser = SmsInboundSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        _msg, result = ingest_sms(
            device=request.auth,
            raw_text=ser.validated_data["text"],
            sender=ser.validated_data.get("sender"),
            received_at=ser.validated_data.get("received_at"),
        )
        return Response(result, status=status.HTTP_201_CREATED)


class SmsPingView(APIView):
    authentication_classes = [SmsDeviceAuthentication]
    permission_classes = [IsSmsDevice]

    @extend_schema(responses=dict, summary="Device token check / heartbeat")
    def get(self, request):
        device = request.auth
        return Response({"device": device.name, "server_time": timezone.now().isoformat()})
