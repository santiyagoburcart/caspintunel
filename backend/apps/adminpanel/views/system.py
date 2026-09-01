import logging
from pathlib import Path

import requests
from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response

from apps.common.models import write_audit

from .base import AdminAPIView

log = logging.getLogger("caspintunel")


def _version_tuple(v):
    try:
        return tuple(int(x) for x in str(v).strip().split("."))
    except ValueError:
        return (0,)


def _latest_version():
    if not settings.UPDATE_CHECK_URL:
        return None
    try:
        r = requests.get(settings.UPDATE_CHECK_URL, timeout=5)
        if r.ok:
            return r.text.strip().splitlines()[0].strip()
    except requests.RequestException as exc:
        log.info("update check failed: %s", exc)
    return None


class SystemView(AdminAPIView):
    perms_map = {"GET": ["monitoring.view"], "POST": ["settings.manage"]}

    @extend_schema(summary="Deployed version + update availability", responses=dict)
    def get(self, request):
        current = settings.VERSION
        latest = _latest_version()
        sentinel = Path(settings.UPDATE_SENTINEL_PATH)
        return Response({
            "version": current,
            "latest_version": latest,
            "update_available": bool(latest and _version_tuple(latest) > _version_tuple(current)),
            "update_requested": sentinel.exists(),
            "update_command": "./update.sh --prod",
        })

    @extend_schema(summary="Request a self-update (host watcher runs update.sh)",
                   request=None, responses=dict)
    def post(self, request):
        sentinel = Path(settings.UPDATE_SENTINEL_PATH)
        try:
            sentinel.parent.mkdir(parents=True, exist_ok=True)
            sentinel.write_text(f"requested {timezone.now().isoformat()} by {request.user}\n")
        except OSError as exc:
            return Response({"detail": f"could not write sentinel: {exc}"}, status=500)
        write_audit(action="system.update_requested", staff=request.user)
        return Response({
            "status": "requested",
            "detail": "the host update watcher will pull and roll out the new version shortly; "
                      "if no watcher is running, run ./update.sh --prod on the server",
        }, status=202)
