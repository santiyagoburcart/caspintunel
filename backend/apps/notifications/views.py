from django.db.models import BooleanField, Case, When
from rest_framework import mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import DeliveryChannel, DeliveryStatus, NotificationDelivery
from .serializers import NotificationDeliverySerializer


class NotificationDeliveryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Site-channel notifications for the logged-in user (the bell dropdown)."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NotificationDeliverySerializer
    queryset = NotificationDelivery.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return NotificationDelivery.objects.none()
        return (
            NotificationDelivery.objects.filter(user=self.request.user, channel=DeliveryChannel.SITE)
            .select_related("notification")
            .annotate(is_read=Case(
                When(status=DeliveryStatus.READ, then=True), default=False, output_field=BooleanField(),
            ))
            .order_by("is_read", "-sent_at")
        )

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        delivery = self.get_object()
        if delivery.status != DeliveryStatus.READ:
            delivery.status = DeliveryStatus.READ
            delivery.save(update_fields=["status"])
        return Response(NotificationDeliverySerializer(delivery).data)

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        updated = (
            NotificationDelivery.objects.filter(user=request.user, channel=DeliveryChannel.SITE)
            .exclude(status=DeliveryStatus.READ)
            .update(status=DeliveryStatus.READ)
        )
        return Response({"updated": updated})

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        from .dispatch import _unread_site_count

        return Response({"unread_count": _unread_site_count(request.user)})
