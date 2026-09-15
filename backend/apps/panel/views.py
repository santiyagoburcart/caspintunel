import io
import logging

import qrcode
from django.http import HttpResponse
from rest_framework import mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .exceptions import PanelError
from .models import Service
from .serializers import ServiceSerializer
from .services import refresh_watchable_services, revoke_subscription, sync_service

log = logging.getLogger("caspintunel")


class ServiceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ServiceSerializer
    queryset = Service.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Service.objects.none()
        return (
            Service.objects.filter(user=self.request.user)
            .select_related("current_plan", "panel")
            .order_by("-created_at")
        )

    def list(self, request, *args, **kwargs):
        # silent, on every load/poll — on_hold flips to active here without any
        # user action (throttled + capped in refresh_watchable_services)
        refresh_watchable_services(list(self.get_queryset()))
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        refresh_watchable_services([self.get_object()])
        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="refresh")
    def refresh(self, request, pk=None):
        """Optional manual force-sync (the list/detail already auto-syncs)."""
        service = self.get_object()
        try:
            sync_service(service.id)
        except PanelError as exc:
            return Response({"detail": str(exc)}, status=502)
        service.refresh_from_db()
        return Response(self.get_serializer(service).data)

    @action(detail=True, methods=["post"], url_path="revoke")
    def revoke(self, request, pk=None):
        """Regenerate the subscription link — disconnects every device using
        the old one. The frontend shows a confirmation warning before calling this."""
        service = self.get_object()
        try:
            revoke_subscription(service.id)
        except PanelError as exc:
            return Response({"detail": str(exc)}, status=502)
        service.refresh_from_db()
        return Response(self.get_serializer(service).data)

    @action(detail=True, methods=["get"], url_path="renew-info")
    def renew_info(self, request, pk=None):
        """Whether this service's current plan can still be bought again —
        the plan may have been deleted or deactivated since the service was
        provisioned/last renewed."""
        service = self.get_object()
        plan = service.current_plan
        if not plan or not plan.is_active:
            return Response({
                "can_renew": False, "plan": None,
                "message": "این پلن دیگر موجود نیست",
            })
        from apps.plans.serializers import PlanSerializer

        return Response({"can_renew": True, "plan": PlanSerializer(plan).data, "message": ""})

    @action(detail=True, methods=["post"], url_path="renew")
    def renew(self, request, pk=None):
        """Creates a paid-pending renewal order for this service's current
        plan — same shape/flow as POST /orders/ (checkout picks up from here);
        provided for completeness/other clients, the web UI itself creates the
        order via the normal checkout flow after showing its own confirmation."""
        from apps.orders.models import OrderType
        from apps.orders.serializers import OrderSerializer
        from apps.orders.services import OrderError, create_order
        from apps.payments_sms.models import BankCard
        from apps.payments_sms.serializers import BankCardSerializer

        service = self.get_object()
        plan = service.current_plan
        if not plan or not plan.is_active:
            return Response({"detail": "این پلن دیگر موجود نیست"}, status=400)

        try:
            order = create_order(
                user=request.user, plan_id=plan.id, order_type=OrderType.RENEW,
                service_id=service.id, source="site",
            )
        except OrderError as exc:
            return Response({"detail": str(exc)}, status=400)

        order_data = OrderSerializer(order).data
        cards = BankCard.objects.filter(is_active=True).order_by("sort_order", "id")
        return Response({
            "order": order_data,
            "payment_instructions": {
                "amount_to_pay": order_data["amount_unique"],
                "reserved_until": order_data["unique_expire_at"],
                "cards": BankCardSerializer(cards, many=True).data,
            },
        }, status=201)

    @action(detail=True, methods=["get"], url_path="qr")
    def qr(self, request, pk=None):
        service = self.get_object()
        if not service.subscription_url:
            return HttpResponse(status=404)
        img = qrcode.make(service.subscription_url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        resp = HttpResponse(buf.getvalue(), content_type="image/png")
        resp["Cache-Control"] = "private, max-age=60"
        return resp
