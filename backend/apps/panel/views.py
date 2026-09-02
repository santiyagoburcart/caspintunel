import io
import logging

import qrcode
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .exceptions import PanelError
from .models import Service, ServiceStatus
from .serializers import ServiceSerializer
from .services import sync_service

log = logging.getLogger("caspintunel")

# statuses whose panel state can change the moment the user connects — refresh
# these on demand when the customer opens their list/detail (but not more than
# once a minute, to avoid hammering the panel on every page load).
_REFRESH_ON_VIEW = (ServiceStatus.ON_HOLD, ServiceStatus.PENDING)
_REFRESH_STALE_SECONDS = 60


def _refresh_if_stale(service: Service) -> None:
    if service.status not in _REFRESH_ON_VIEW:
        return
    if service.last_synced_at and (timezone.now() - service.last_synced_at).total_seconds() < _REFRESH_STALE_SECONDS:
        return
    try:
        sync_service(service.id)
    except PanelError as exc:
        log.info("on-view sync of service %s skipped: %s", service.id, exc)
    except Exception as exc:  # noqa: BLE001 - a panel hiccup must not break the page
        log.warning("on-view sync of service %s failed: %s", service.id, exc)


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
        for svc in self.get_queryset():
            _refresh_if_stale(svc)
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        _refresh_if_stale(self.get_object())
        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="refresh")
    def refresh(self, request, pk=None):
        """Force a fresh panel sync for this service (used after 'I connected')."""
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
