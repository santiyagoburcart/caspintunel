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
        return Response(
            {"status": "ok" if ok else "degraded", "version": settings.VERSION, "checks": checks},
            status=200 if ok else 503,
        )
