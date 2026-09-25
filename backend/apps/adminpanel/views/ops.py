import logging

from django.db.models import Count, Max, Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.panel.exceptions import PanelError
from apps.panel.models import Service, ServiceStatus
from apps.panel.services import (
    client_for,
    create_manual_service,
    delete_service,
    reset_service_usage,
    revoke_subscription,
    set_service_status,
    update_service,
)
from apps.telegram.models import RequiredChannel, TelegramStats

from ..permissions import StaffPermission
from ..serializers import (
    AdminServiceCreateSerializer,
    AdminServiceRawSerializer,
    AdminServiceSerializer,
    AdminServiceStatusSerializer,
    AdminServiceUpdateSerializer,
)
from .base import AdminAPIView, _AUTH

log = logging.getLogger("caspintunel")
ONLINE_WINDOW_MIN = 5


class ServiceListViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                         mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """/admin/services/ — the standalone "sold services" admin page: list +
    search/filter, manual creation, and per-row status/reset/revoke/delete/details."""

    authentication_classes = _AUTH
    permission_classes = [StaffPermission]
    perms_map = {
        "GET": ["monitoring.view"], "POST": ["services.manage"],
        "PATCH": ["services.manage"], "DELETE": ["services.delete"],
    }
    queryset = Service.objects.none()
    serializer_class = AdminServiceSerializer

    def get_queryset(self):
        qs = Service.objects.select_related("user", "current_plan", "panel", "scheduled_renewal").order_by("-created_at")
        kind = self.request.query_params.get("filter")
        if kind == "active":
            qs = qs.filter(status=ServiceStatus.ACTIVE)
        elif kind == "on_hold":
            qs = qs.filter(status=ServiceStatus.ON_HOLD)
        elif kind == "disabled":
            qs = qs.filter(status=ServiceStatus.DISABLED)
        elif kind == "expired":
            qs = qs.filter(status=ServiceStatus.EXPIRED)
        elif kind == "online":
            since = timezone.now() - timezone.timedelta(minutes=ONLINE_WINDOW_MIN)
            qs = qs.filter(online_at__gte=since)

        q = (self.request.query_params.get("search") or "").strip()
        if q:
            qs = qs.filter(
                Q(panel_username__icontains=q) | Q(user__username__icontains=q)
                | Q(user__name__icontains=q) | Q(user__telegram_username__icontains=q)
            )
        return qs

    def get_serializer_class(self):
        return AdminServiceCreateSerializer if self.action == "create" else AdminServiceSerializer

    def list(self, request, *args, **kwargs):
        resp = super().list(request, *args, **kwargs)
        resp.data["last_synced_at"] = Service.objects.aggregate(m=Max("last_synced_at"))["m"]
        by_status = dict(Service.objects.values_list("status").annotate(n=Count("id")).values_list("status", "n"))
        resp.data["stats"] = {
            "total": sum(by_status.values()),
            "active": by_status.get(ServiceStatus.ACTIVE, 0),
            "on_hold": by_status.get(ServiceStatus.ON_HOLD, 0),
            "disabled": by_status.get(ServiceStatus.DISABLED, 0),
        }
        return resp

    def create(self, request, *args, **kwargs):
        """Manual service creation (فاز ۲) — no payment, real panel account."""
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        try:
            service = create_manual_service(
                user=v["user"], plan=v["plan"], panel=v.get("panel"),
                group_ids=v.get("group_ids"), account_name=v.get("account_name"),
                staff=request.user,
            )
        except PanelError as exc:
            return Response({"detail": str(exc)}, status=502)
        return Response(AdminServiceSerializer(service).data, status=201)

    @action(detail=True, methods=["post"], url_path="status")
    def change_status(self, request, pk=None):
        ser = AdminServiceStatusSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            service = set_service_status(int(pk), ser.validated_data["status"], staff=request.user)
        except PanelError as exc:
            return Response({"detail": str(exc)}, status=502)
        return Response(AdminServiceSerializer(service).data)

    @action(detail=True, methods=["post"], url_path="reset")
    def reset_usage(self, request, pk=None):
        try:
            service = reset_service_usage(int(pk), staff=request.user)
        except PanelError as exc:
            return Response({"detail": str(exc)}, status=502)
        return Response(AdminServiceSerializer(service).data)

    @action(detail=True, methods=["post"], url_path="revoke")
    def revoke(self, request, pk=None):
        try:
            service = revoke_subscription(int(pk), staff=request.user)
        except PanelError as exc:
            return Response({"detail": str(exc)}, status=502)
        return Response(AdminServiceSerializer(service).data)

    @extend_schema(request=AdminServiceUpdateSerializer, responses=AdminServiceRawSerializer,
                   summary="Edit a service on the panel (status, volume, expiry, groups, note)")
    def partial_update(self, request, pk=None):
        from datetime import datetime, time
        from zoneinfo import ZoneInfo

        service = self.get_object()
        ser = AdminServiceUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        kw = {}
        if "status" in v:
            kw["status"] = v["status"]
        if "data_limit_gb" in v:
            kw["data_limit"] = int(v["data_limit_gb"] * 1024 ** 3)
        if "expire_date" in v:
            d = v["expire_date"]
            kw["expire_at"] = (datetime.combine(d, time(23, 59, 59), tzinfo=ZoneInfo("Asia/Tehran"))
                               if d else None)
        for key in ("on_hold_days", "group_ids", "note"):
            if key in v:
                kw[key] = v[key]
        try:
            service, raw = update_service(service.id, staff=request.user, **kw)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        except PanelError as exc:
            return Response({"detail": str(exc)}, status=502)
        return Response(AdminServiceRawSerializer(service, context={"panel_raw": raw}).data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            delete_service(instance.id, staff=request.user)
        except PanelError as exc:
            return Response({"detail": str(exc)}, status=502)
        return Response(status=204)

    @action(detail=True, methods=["get"], url_path="panel-detail")
    def panel_detail(self, request, pk=None):
        """Everything PasarGuard returns for this account, live — the
        "جزئیات" modal (raw + our formatted fields in one response)."""
        service = self.get_object()
        raw = None
        try:
            raw = client_for(service.panel).get_user(service.panel_username)
        except PanelError as exc:
            log.info("panel-detail live fetch failed for service %s: %s", service.id, exc)
        data = AdminServiceRawSerializer(service, context={"panel_raw": raw}).data
        return Response(data)

    @action(detail=False, methods=["post"], url_path="sync-now")
    def sync_now(self, request):
        from apps.panel.tasks import sync_all_services

        result = sync_all_services.delay()
        return Response({"detail": "sync dispatched", "task_id": result.id}, status=202)


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
