import time

import psutil
from django.conf import settings
from django.core.cache import cache
from django.db.models import Avg, Max
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.ops.models import BackupLog, HealthCheck, HealthTarget, ResourceStat

from .. import hostnet
from ..permissions import StaffPermission
from ..serializers import BackupLogSerializer, HealthCheckSerializer, ResourceStatSerializer
from .base import AdminAPIView, _AUTH

_GB = 1024 ** 3
_SERIES_KEY = "mon:net:series"
_NET_KEY = "mon:net:last"
_PUBIP_KEY = "mon:public_ip"


class HealthView(AdminAPIView):
    perms_map = {"GET": ["monitoring.view"]}

    @extend_schema(responses=HealthCheckSerializer(many=True),
                   summary="Latest status for every monitored target")
    def get(self, request):
        return Response(_health_snapshot())


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


class MonitoringView(AdminAPIView):
    """One live snapshot for the admin Monitoring page (polled every ~15 s)."""

    perms_map = {"GET": ["monitoring.view"]}

    @extend_schema(responses=dict, summary="Live monitoring snapshot")
    def get(self, request):
        health = _health_snapshot()
        return Response({
            "version": settings.VERSION,
            "overall": health["overall"],
            "up_count": sum(1 for t in health["targets"] if t["is_up"]),
            "total_count": len(health["targets"]),
            "targets": health["targets"],
            "resources": _resources_snapshot(),
            "network": _network_snapshot(),
            "server": _server_snapshot(),
            "backups": BackupLogSerializer(
                BackupLog.objects.order_by("-created_at")[:6], many=True
            ).data,
        })


# --------------------------------------------------------------------------
def _health_snapshot() -> dict:
    latest_ids = (
        HealthCheck.objects.values("target")
        .annotate(last=Max("id")).values_list("last", flat=True)
    )
    rows = {c.target: c for c in HealthCheck.objects.filter(id__in=list(latest_ids))}
    targets = []
    for target in HealthTarget.values:
        c = rows.get(target)
        targets.append({
            "target": target,
            "is_up": bool(c.is_up) if c else None,
            "latency_ms": c.latency_ms if c else None,
            "detail": c.detail if c else "no data yet",
            "checked_at": c.checked_at if c else None,
        })
    healthy = all(t["is_up"] for t in targets if t["is_up"] is not None)
    return {"overall": "ok" if healthy else "degraded", "targets": targets}


def _resources_snapshot() -> dict:
    vm = psutil.virtual_memory()
    try:
        du = psutil.disk_usage(settings.RESOURCE_DISK_PATH)
    except OSError:
        du = psutil.disk_usage("/")
    freq = psutil.cpu_freq()
    agg = ResourceStat.objects.filter(
        sampled_at__gte=timezone.now() - timezone.timedelta(hours=24)
    ).aggregate(
        cpu_avg=Avg("cpu_percent"), cpu_max=Max("cpu_percent"),
        ram_avg=Avg("ram_percent"), ram_max=Max("ram_percent"),
    )
    return {
        "cpu": {
            "percent": round(psutil.cpu_percent(interval=0.3), 1),
            "cores": psutil.cpu_count(logical=True),
            "freq_ghz": round((freq.current or 0) / 1000, 2) if freq else None,
            "avg": round(agg["cpu_avg"] or 0, 1),
            "peak": round(agg["cpu_max"] or 0, 1),
        },
        "ram": {
            "percent": round(vm.percent, 1),
            "used_gb": round(vm.used / _GB, 2),
            "total_gb": round(vm.total / _GB, 2),
            "avg": round(agg["ram_avg"] or 0, 1),
            "peak": round(agg["ram_max"] or 0, 1),
        },
        "disk": {
            "percent": round(du.percent, 1),
            "used_gb": round(du.used / _GB, 1),
            "total_gb": round(du.total / _GB, 1),
            "free_gb": round(du.free / _GB, 1),
        },
    }


def _network_snapshot() -> dict:
    c = hostnet.iface_counters()
    now = time.monotonic()
    sent, recv = c["tx_bytes"], c["rx_bytes"]

    prev = cache.get(_NET_KEY)
    up_bps = down_bps = 0
    if prev:
        p_t, p_sent, p_recv = prev
        dt = now - p_t
        if dt > 0 and sent >= p_sent and recv >= p_recv:
            up_bps = int((sent - p_sent) / dt)
            down_bps = int((recv - p_recv) / dt)
    cache.set(_NET_KEY, (now, sent, recv), 300)

    series = cache.get(_SERIES_KEY) or []
    series.append({
        "t": timezone.now().strftime("%H:%M:%S"),
        "up": up_bps, "down": down_bps,
    })
    series = series[-40:]
    cache.set(_SERIES_KEY, series, 600)

    return {
        "iface": c["iface"],
        "up_bps": up_bps,
        "down_bps": down_bps,
        "sent_total": sent,
        "recv_total": recv,
        "series": series,
    }


def _public_ip() -> str:
    if getattr(settings, "SERVER_IP", ""):
        return settings.SERVER_IP
    cached = cache.get(_PUBIP_KEY)
    if cached:
        return cached
    try:
        import requests

        ip = requests.get("https://api.ipify.org", timeout=4).text.strip()
        cache.set(_PUBIP_KEY, ip, 3600)
        return ip
    except Exception:  # noqa: BLE001
        return ""


def _server_snapshot() -> dict:
    pub = _public_ip()
    locals_ = [ip for ip in hostnet.local_ips() if ip != pub]
    docker_ips = [ip for ip in locals_ if ip.startswith(("172.1", "172.2", "172.3"))]
    lan_ips = [ip for ip in locals_ if ip not in docker_ips]
    socks = hostnet.socket_counts()
    return {
        "public_ip": pub,
        "local_ips": lan_ips or ["—"],
        "docker_ips": docker_ips or hostnet.gateways() or ["—"],
        "tcp_open": socks["tcp"],
        "udp_open": socks["udp"],
    }
