import logging
from pathlib import Path

import requests
from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response

from apps.common.models import write_audit
from apps.settings_app.utils import get_setting, set_setting

from .base import AdminAPIView

log = logging.getLogger("caspintunel")

# The runtime settings the operator may change from the panel. Order = UI order.
EDITABLE_SETTINGS = [
    # key, type, default, min, max  (min/max advisory, enforced for ints)
    ("backup_interval_minutes", "int", 1440, 5, 43200),
    ("service_sync_interval_minutes", "int", 60, 1, 1440),
    ("unique_amount_reservation_minutes", "int", 30, 5, 720),
    ("unique_amount_min", "int", 200, 1, 100000),
    ("unique_amount_max", "int", 1500, 1, 100000),
    ("alert_volume_percent", "int", 80, 1, 100),
    ("alert_expire_days", "int", 3, 1, 60),
    ("email_verification_required", "bool", False, None, None),
    ("referral_required", "bool", False, None, None),
    ("force_channel_join", "bool", False, None, None),
    ("force_share_phone", "bool", False, None, None),
    ("default_language", "str", "fa", None, None),
    ("product_display_mode", "str", "grouped", None, None),
]
_SPEC = {k: (t, d, lo, hi) for (k, t, d, lo, hi) in EDITABLE_SETTINGS}

# str settings restricted to a fixed choice set
_ENUM = {
    "default_language": {"fa", "en"},
    "product_display_mode": {"grouped", "flat"},
}


class SettingsView(AdminAPIView):
    """GET / PUT the runtime key-value settings the operator is allowed to touch
    (backup interval, reservation window, alert thresholds, verification toggle …)."""

    perms_map = {"GET": ["settings.manage"], "PUT": ["settings.manage"], "PATCH": ["settings.manage"]}

    @extend_schema(responses=dict, summary="Runtime settings")
    def get(self, request):
        return Response({"settings": [
            {"key": k, "type": t, "value": get_setting(k, d)}
            for (k, t, d, _lo, _hi) in EDITABLE_SETTINGS
        ]})

    @extend_schema(request=dict, responses=dict, summary="Update runtime settings")
    def put(self, request):
        changed = []
        for key, raw in (request.data or {}).items():
            spec = _SPEC.get(key)
            if not spec:
                continue  # ignore unknown / read-only keys
            vtype, default, lo, hi = spec
            try:
                if vtype == "int":
                    val = int(raw)
                    if lo is not None:
                        val = max(lo, min(hi, val))
                elif vtype == "bool":
                    val = str(raw).strip().lower() in ("1", "true", "yes", "on") or raw is True
                    val = "true" if val else "false"
                else:
                    val = str(raw).strip()
                    if key in _ENUM and val not in _ENUM[key]:
                        return Response(
                            {"detail": f"{key} must be one of {sorted(_ENUM[key])}"}, status=400)
            except (TypeError, ValueError):
                return Response({"detail": f"bad value for {key}"}, status=400)
            set_setting(key, val, vtype)
            changed.append(key)
        if changed:
            write_audit(action="settings.updated", staff=request.user, detail={"keys": changed})
        return self.get(request)

    patch = put


def _version_tuple(v):
    try:
        return tuple(int(x) for x in str(v).strip().split("."))
    except ValueError:
        return (0,)


def _latest_version():
    token = getattr(settings, "GITHUB_TOKEN", "")
    owner = getattr(settings, "GITHUB_OWNER", "")
    repo = getattr(settings, "GITHUB_REPO", "")
    try:
        if token and owner and repo:  # works for private repos
            r = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}/contents/VERSION",
                headers={"Authorization": f"Bearer {token}",
                         "Accept": "application/vnd.github.raw+json"},
                timeout=5,
            )
        elif settings.UPDATE_CHECK_URL:
            r = requests.get(settings.UPDATE_CHECK_URL, timeout=5)
        else:
            return None
        if r.ok and r.text.strip():
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
