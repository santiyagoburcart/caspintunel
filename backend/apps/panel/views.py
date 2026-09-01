import io

import qrcode
from django.http import HttpResponse
from rest_framework import mixins, permissions, viewsets
from rest_framework.decorators import action

from .models import Service
from .serializers import ServiceSerializer


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

    @action(detail=True, methods=["get"], url_path="qr")
    def qr(self, request, pk=None):
        service = self.get_object()
        if not service.subscription_url:
            return HttpResponse(status=404)
        img = qrcode.make(service.subscription_url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return HttpResponse(buf.getvalue(), content_type="image/png")
