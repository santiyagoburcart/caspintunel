import mimetypes

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.accounts.models import Staff
from apps.adminpanel.permissions import StaffJWTAuthentication
from apps.orders.models import Order

from .authentication import IsSmsDevice, SmsDeviceAuthentication
from .matching import ingest_sms
from .models import BankCard, Payment, PaymentStatus, SmsSource
from .serializers import (
    BankCardSerializer,
    PaymentSerializer,
    ReceiptUploadSerializer,
    RejectSerializer,
    SmsInboundSerializer,
)
from .services import PaymentError, approve_payment, reject_payment, submit_receipt


def _bank_card_from_request(request) -> BankCard | None:
    """Optional `bank_card` id in the approve request body — lets the admin say
    which card this deposit actually landed on (drives the per-card report)."""
    raw = request.data.get("bank_card")
    if raw in (None, "", 0, "0"):
        return None
    return BankCard.objects.filter(pk=raw).first()


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


class ReceiptFileView(APIView):
    """Serve a payment receipt image to its owner (customer) or to a panel
    operator with `payment.view` only.

    In prod (`SERVE_MEDIA_VIA_XACCEL`) hands off to nginx via X-Accel-Redirect;
    in dev it streams the file directly. Either way the media path is never a
    public, guessable URL — access is checked here first."""

    authentication_classes = [
        StaffJWTAuthentication,
        JWTAuthentication,
        SessionAuthentication,
    ]
    permission_classes = [permissions.AllowAny]  # authorised explicitly below

    def get(self, request, pk):
        payment = get_object_or_404(
            Payment.objects.select_related("order", "order__user"), pk=pk
        )
        user = request.user
        if isinstance(user, Staff):
            allowed = user.is_superadmin or user.has_perm("payment.view")
        elif getattr(user, "is_authenticated", False):
            allowed = payment.order.user_id == user.id or getattr(user, "is_staff", False)
        else:
            return Response({"detail": "authentication required"}, status=401)
        if not allowed or not payment.receipt_image:
            raise Http404

        name = payment.receipt_image.name  # e.g. "receipts/2026/09/foo.jpg"
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"

        if getattr(settings, "SERVE_MEDIA_VIA_XACCEL", False):
            resp = HttpResponse(content_type=ctype)
            resp["X-Accel-Redirect"] = f"/_protected_media/{name}"
            resp["Content-Disposition"] = "inline"
            return resp
        try:
            fh = payment.receipt_image.open("rb")
        except FileNotFoundError as exc:
            raise Http404 from exc
        resp = FileResponse(fh, content_type=ctype)
        resp["Content-Disposition"] = "inline"
        resp["Cache-Control"] = "private, max-age=0, no-store"
        return resp


class PaymentApproveView(APIView):
    permission_classes = [permissions.IsAdminUser]

    @extend_schema(request=None, responses=PaymentSerializer, summary="Approve a pending payment")
    def post(self, request, pk):
        try:
            payment = approve_payment(
                pk, actor=request.user, bank_card=_bank_card_from_request(request)
            )
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


class SmsSourcesView(APIView):
    """The bank sender numbers the Android app should forward SMS from — the
    same allow-list `_resolve_source` matches against server-side. The app
    caches this and filters locally so it isn't uploading every SMS on the
    phone, only the ones that could plausibly be a deposit notification."""

    authentication_classes = [SmsDeviceAuthentication]
    permission_classes = [IsSmsDevice]

    @extend_schema(responses=dict, summary="Allowed SMS sender numbers for this device")
    def get(self, request):
        sources = SmsSource.objects.filter(is_active=True).order_by("id")
        return Response({
            "sources": [
                {"phone_number": s.phone_number, "description": s.description}
                for s in sources
            ],
        })
