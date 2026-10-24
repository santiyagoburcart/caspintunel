from django.conf import settings
from django.db import connection
from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class ApiRootView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary="API root / metadata", responses=dict)
    def get(self, request):
        return Response(
            {
                "name": "caspintunel API",
                "version": settings.VERSION,
                "api": "v1",
                "docs": request.build_absolute_uri("/api/docs/"),
                "schema": request.build_absolute_uri("/api/schema/"),
            }
        )


class HealthView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary="Liveness/readiness probe", responses=dict)
    def get(self, request):
        checks = {}

        try:
            with connection.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            checks["database"] = True
        except Exception:  # noqa: BLE001 - report, never crash
            checks["database"] = False

        try:
            cache.set("health:ping", "1", 5)
            checks["redis"] = cache.get("health:ping") == "1"
        except Exception:  # noqa: BLE001
            checks["redis"] = False

        ok = all(checks.values())
        resp = Response(
            {"status": "ok" if ok else "degraded", "version": settings.VERSION, "checks": checks},
            status=200 if ok else 503,
        )
        from apps.settings_app.access import instance_id

        resp["X-Caspin-Instance"] = instance_id()    # access-mode checks: the answer came from THIS server
        return resp


class DomainProbeView(APIView):
    """Access mode → "Auto-detect": a test request through the tunnel records the
    TCP peer address nginx saw (X-Conn-Addr). Only for a nonce the panel created."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "public_read"

    @extend_schema(exclude=True)
    def get(self, request, nonce):
        from apps.settings_app.access import instance_id, record_probe

        row = record_probe(nonce, request)
        if row is None:
            return Response({"detail": "unknown probe"}, status=404)
        resp = Response({"ok": True, "conn": row["conn"], "client": row["client"]})
        resp["X-Caspin-Instance"] = instance_id()
        return resp
