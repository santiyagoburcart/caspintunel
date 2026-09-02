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
from .services import refresh_watchable_services, sync_service

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
