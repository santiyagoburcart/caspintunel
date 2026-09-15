from django.db.models import Count
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.response import Response

from apps.panel.models import Service, ServiceStatus
from apps.telegram.models import RequiredChannel, TelegramStats

from ..permissions import StaffPermission
from ..serializers import AdminServiceSerializer
from .base import AdminAPIView, _AUTH

ONLINE_WINDOW_MIN = 5


class ServiceListViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    authentication_classes = _AUTH
    permission_classes = [StaffPermission]
    perms_map = {"GET": ["monitoring.view"]}
    queryset = Service.objects.none()
    serializer_class = AdminServiceSerializer

    def get_queryset(self):
        qs = Service.objects.select_related("user", "current_plan", "scheduled_renewal").order_by("-created_at")
        kind = self.request.query_params.get("filter")
        if kind == "expired":
            qs = qs.filter(status=ServiceStatus.EXPIRED)
        elif kind == "on_hold":
            qs = qs.filter(status=ServiceStatus.ON_HOLD)
        elif kind == "online":
            since = timezone.now() - timezone.timedelta(minutes=ONLINE_WINDOW_MIN)
            qs = qs.filter(online_at__gte=since)
        return qs


class DashboardView(AdminAPIView):
    perms_map = {"GET": ["monitoring.view"]}

    @extend_schema(summary="Panel overview counters", responses=dict)
    def get(self, request):
        from django.db.models import Max

        from apps.ops.models import HealthCheck, ResourceStat

        by_status = dict(
            Service.objects.values_list("status").annotate(n=Count("id")).values_list("status", "n")
        )
        since = timezone.now() - timezone.timedelta(minutes=ONLINE_WINDOW_MIN)

        latest_ids = HealthCheck.objects.values("target").annotate(last=Max("id")).values_list("last", flat=True)
        checks = list(HealthCheck.objects.filter(id__in=list(latest_ids)))
        res = ResourceStat.objects.order_by("-sampled_at").first()

        return Response({
            "services": {
                "total": sum(by_status.values()),
                "by_status": by_status,
                "online_now": Service.objects.filter(online_at__gte=since).count(),
            },
            "health": {
                "up": sum(1 for c in checks if c.is_up),
                "down": [c.target for c in checks if not c.is_up],
            },
            "resources": {
                "cpu_percent": res.cpu_percent if res else None,
                "ram_percent": res.ram_percent if res else None,
                "disk_percent": res.disk_percent if res else None,
                "sampled_at": res.sampled_at if res else None,
            },
        })


class TelegramStatsView(AdminAPIView):
    perms_map = {"GET": ["monitoring.view"]}

    @extend_schema(summary="Forced-channel member counts + latest bot stats", responses=dict)
    def get(self, request):
        channels = list(
            RequiredChannel.objects.filter(is_active=True)
            .values("channel_id", "title", "member_count", "last_synced_at")
        )
        latest = TelegramStats.objects.order_by("-sampled_at").first()
        return Response({
            "channels": channels,
            "channel_total": sum(c["member_count"] for c in channels),
            "bot_member_count": latest.bot_member_count if latest else None,
            "overlap_bot_channels": latest.overlap_bot_channels if latest else None,
            "sampled_at": latest.sampled_at if latest else None,
        })
