from django.db.models import Max
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.ops.models import BackupLog, HealthCheck, HealthTarget, ResourceStat

from ..permissions import StaffPermission
from ..serializers import BackupLogSerializer, HealthCheckSerializer, ResourceStatSerializer
from .base import AdminAPIView, _AUTH


class HealthView(AdminAPIView):
    perms_map = {"GET": ["monitoring.view"]}

    @extend_schema(responses=HealthCheckSerializer(many=True),
                   summary="Latest status for every monitored target")
    def get(self, request):
        latest_ids = (
            HealthCheck.objects.values("target")
            .annotate(last=Max("id"))
            .values_list("last", flat=True)
        )
        rows = {c.target: c for c in HealthCheck.objects.filter(id__in=list(latest_ids))}
        out = []
        for target in HealthTarget.values:
            check = rows.get(target)
            out.append(
                HealthCheckSerializer(check).data if check
                else {"target": target, "is_up": None, "detail": "no data yet"}
            )
        healthy = all(r["is_up"] for r in out if r["is_up"] is not None)
        return Response({"overall": "ok" if healthy else "degraded", "targets": out})


class ResourcesView(AdminAPIView):
    perms_map = {"GET": ["monitoring.view"]}

    @extend_schema(responses=dict, summary="Latest + recent server resource samples")
    def get(self, request):
        limit = min(int(request.query_params.get("limit", 60)), 500)
        recent = ResourceStat.objects.order_by("-sampled_at")[:limit]
        latest = recent[0] if recent else None
        return Response({
            "latest": ResourceStatSerializer(latest).data if latest else None,
            "series": ResourceStatSerializer(reversed(list(recent)), many=True).data,
        })


class BackupViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    authentication_classes = _AUTH
    permission_classes = [StaffPermission]
    perms_map = {"GET": ["monitoring.view"], "POST": ["settings.manage"]}
    queryset = BackupLog.objects.order_by("-created_at")
    serializer_class = BackupLogSerializer

    @action(detail=False, methods=["post"], url_path="run")
    def run(self, request):
        from apps.telegram.tasks import run_backup_task

        run_backup_task.delay()
        return Response({"detail": "backup started"}, status=202)
