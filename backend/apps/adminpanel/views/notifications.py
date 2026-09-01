from django.contrib.auth import get_user_model
from django.db.models import Count
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.response import Response

from apps.notifications.models import Notification, NotificationType

from ..permissions import StaffPermission
from ..serializers import BroadcastSerializer, NotificationSerializer
from .base import _AUTH

User = get_user_model()


class NotificationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                          mixins.CreateModelMixin, viewsets.GenericViewSet):
    authentication_classes = _AUTH
    permission_classes = [StaffPermission]
    perms_map = {"GET": ["broadcast.send"], "POST": ["broadcast.send"]}
    queryset = Notification.objects.none()
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return (
            Notification.objects.annotate(delivery_count=Count("deliveries"))
            .order_by("-created_at")
        )

    @extend_schema(request=BroadcastSerializer, responses=NotificationSerializer,
                   summary="Create a broadcast / targeted notification (site/bot/email)")
    def create(self, request, *args, **kwargs):
        ser = BroadcastSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        target_id = data.get("target_user")
        staff = request.user if hasattr(request.user, "role") else None
        note = Notification.objects.create(
            type=NotificationType.EVENT if target_id else NotificationType.BROADCAST,
            title=data["title"],
            body=data["body"],
            target_user_id=target_id,
            via_site=data["via_site"],
            via_bot=data["via_bot"],
            via_email=data["via_email"],
            created_by_staff=staff,
        )
        from django.db import transaction

        from apps.notifications.tasks import deliver_notification_task

        transaction.on_commit(lambda: deliver_notification_task.delay(note.id))

        audience = 1 if target_id else User.objects.filter(is_active=True).count()
        return Response(
            {**NotificationSerializer(note).data, "audience": audience, "delivery": "queued"},
            status=201,
        )
