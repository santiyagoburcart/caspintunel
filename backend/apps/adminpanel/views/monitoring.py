import os
import time

import psutil
from django.conf import settings
from django.core.cache import cache
from django.db.models import Max
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
_CONN_SERIES_KEY = "mon:conn:series"
_SPARK_POINTS = 30
_RES_HISTORY_HOURS = 24


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
            "panels": health["panels"],
            "resources": _resources_snapshot(),
            "network": _network_snapshot(),
            "connections": _connections_snapshot(),
            "process": _process_snapshot(),
            "server": _server_snapshot(),
            "backups": BackupLogSerializer(
                BackupLog.objects.order_by("-created_at")[:6], many=True
            ).data,
        })


# --------------------------------------------------------------------------
def _health_snapshot() -> dict:
    # non-panel targets: latest row per target
    non_panel = HealthCheck.objects.exclude(target=HealthTarget.PANEL)
    latest_ids = (
        non_panel.values("target").annotate(last=Max("id")).values_list("last", flat=True)
    )
    rows = {c.target: c for c in HealthCheck.objects.filter(id__in=list(latest_ids))}
    # the "panel" line in the main list = latest aggregate row (panel_id IS NULL)
    agg = (
        HealthCheck.objects.filter(target=HealthTarget.PANEL, panel__isnull=True)
        .order_by("-id").first()
    )
    if agg:
        rows[HealthTarget.PANEL] = agg

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
    return {
        "overall": "ok" if healthy else "degraded",
        "targets": targets,
        "panels": _panel_health_rows(),
    }


def _panel_health_rows() -> list[dict]:
    """Per-panel health (from the latest stored check) + a live, cached stats
    blob. Never raises; the panel name is admin-only so exposing it is fine."""
    from apps.panel.models import Panel

    out = []
    for panel in Panel.objects.filter(is_active=True).order_by("id"):
        c = (
            HealthCheck.objects.filter(target=HealthTarget.PANEL, panel=panel)
            .order_by("-id").first()
        )
        healthy = bool(c and c.is_up)
        out.append({
            "id": panel.id,
            "name": panel.name,
            "base_url": panel.base_url,
            "is_up": bool(c.is_up) if c else None,
            "latency_ms": c.latency_ms if c else None,
            "detail": c.detail if c else "no data yet",
            "checked_at": c.checked_at if c else None,
            # only hit a panel that the last health check said is reachable, so a
            # down panel never makes this endpoint hang on a timeout
            "stats": _panel_stats(panel) if healthy else None,
        })
    return out


def _panel_stats(panel) -> dict | None:
    """Live node/system stats for one panel — cached 60 s, best-effort."""
    key = f"mon:panel_stats:{panel.id}"
    cached = cache.get(key)
    if cached is not None:
        return cached or None
    stats = {}
    try:
        from apps.panel.services import client_for

        client = client_for(panel)
        s = client.system_stats() or {}
        stats = {
            "version": s.get("version"),
            "users_total": s.get("total_user"),
            "users_active": s.get("users_active"),
            "users_online": s.get("online_users") or s.get("users_online"),
            "mem_used": s.get("mem_used"),
            "mem_total": s.get("mem_total"),
            "cpu_usage": s.get("cpu_usage"),
            "cpu_cores": s.get("cpu_cores"),
            "incoming_bandwidth": s.get("incoming_bandwidth"),
            "outgoing_bandwidth": s.get("outgoing_bandwidth"),
        }
        try:
            nodes = client.list_nodes() or []
            stats["nodes"] = [
                {"name": n.get("name"), "status": n.get("status"),
                 "xray_version": n.get("xray_version")}
                for n in nodes if isinstance(n, dict)
            ]
        except Exception:  # noqa: BLE001 - nodes endpoint is optional
            pass
        stats = {k: v for k, v in stats.items() if v is not None}
    except Exception:  # noqa: BLE001 - panel down / stats unsupported
        stats = {}
    cache.set(key, stats, 60)
    return stats or None


def _metric_history(rows: list[dict], key: str) -> dict:
    """avg/peak over the lookback window + a short series for the sparkline."""
    vals = [r[key] for r in rows] or [0.0]
    return {
        "avg": round(sum(vals) / len(vals), 1),
        "peak": round(max(vals), 1),
        "series": [round(v, 1) for v in vals[-_SPARK_POINTS:]],
    }


def _resources_snapshot() -> dict:
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()
    try:
        du = psutil.disk_usage(settings.RESOURCE_DISK_PATH)
    except OSError:
        du = psutil.disk_usage("/")
    freq = psutil.cpu_freq()

    since = timezone.now() - timezone.timedelta(hours=_RES_HISTORY_HOURS)
    rows = list(
        ResourceStat.objects.filter(sampled_at__gte=since)
        .order_by("-sampled_at")[:300]
        .values("cpu_percent", "ram_percent", "swap_percent", "disk_percent")
    )
    rows.reverse()  # chronological, oldest first, for the sparkline

    cpu_h, ram_h = _metric_history(rows, "cpu_percent"), _metric_history(rows, "ram_percent")
    swap_h, disk_h = _metric_history(rows, "swap_percent"), _metric_history(rows, "disk_percent")

    return {
        "cpu": {
            "percent": round(psutil.cpu_percent(interval=0.3), 1),
            "cores": psutil.cpu_count(logical=True),
            "freq_ghz": round((freq.current or 0) / 1000, 2) if freq else None,
            **cpu_h,
        },
        "ram": {
            "percent": round(vm.percent, 1),
            "used_gb": round(vm.used / _GB, 2),
            "total_gb": round(vm.total / _GB, 2),
            **ram_h,
        },
        "swap": {
            "percent": round(swap.percent, 1),
            "used_gb": round(swap.used / _GB, 2),
            "total_gb": round(swap.total / _GB, 2),
            **swap_h,
        },
        "disk": {
            "percent": round(du.percent, 1),
            "used_gb": round(du.used / _GB, 1),
            "total_gb": round(du.total / _GB, 1),
            "free_gb": round(du.free / _GB, 1),
            **disk_h,
        },
    }


def _connections_snapshot() -> dict:
    """Open TCP/UDP sockets on the host + a short rolling series (per-poll,
    ~15s cadence, capped to the last 40 points ≈ 10 min)."""
    socks = hostnet.socket_counts()
    tcp, udp = max(socks["tcp"], 0), max(socks["udp"], 0)

    series = cache.get(_CONN_SERIES_KEY) or []
    series.append({"t": timezone.now().strftime("%H:%M:%S"), "tcp": tcp, "udp": udp})
    series = series[-40:]
    cache.set(_CONN_SERIES_KEY, series, 600)

    return {"tcp": tcp, "udp": udp, "total": tcp + udp, "series": series}


def _process_snapshot() -> dict:
    """This backend process's own memory/thread footprint + the two uptimes
    (this process vs. the host OS) — the "Panel" / "Uptime" cards."""
    ram_mb = threads = service_uptime_s = None
    try:
        proc = psutil.Process(os.getpid())
        ram_mb = round(proc.memory_info().rss / (1024 ** 2), 1)
        threads = proc.num_threads()
        service_uptime_s = int(time.time() - proc.create_time())
    except Exception:  # noqa: BLE001
        pass
    try:
        os_uptime_s = int(time.time() - psutil.boot_time())
    except Exception:  # noqa: BLE001
        os_uptime_s = None
    return {
        "ram_mb": ram_mb, "threads": threads,
        "service_uptime_s": service_uptime_s, "os_uptime_s": os_uptime_s,
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
