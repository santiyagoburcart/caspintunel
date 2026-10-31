import logging
from pathlib import Path

import requests
from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response

from apps.common.models import write_audit
from apps.settings_app import shortcut
from apps.settings_app.utils import get_setting, set_setting

from .base import AdminAPIView

log = logging.getLogger("caspintunel")

# The runtime settings the operator may change from the panel. Order = UI order.
EDITABLE_SETTINGS = [
    # key, type, default, min, max  (min/max advisory, enforced for ints)
    ("backup_interval_minutes", "int", 1440, 5, 43200),
    # local copies only; a backup is deleted only after Telegram confirmed it
    ("backup_retention_days", "int", 2, 1, 365),
    ("service_sync_interval_minutes", "int", 60, 1, 1440),
    ("unique_amount_reservation_minutes", "int", 30, 5, 720),
    ("unique_amount_min", "int", 200, 1, 100000),
    ("unique_amount_max", "int", 1500, 1, 100000),
    ("alert_volume_percent", "int", 80, 1, 100),
    ("alert_expire_days", "int", 3, 1, 60),
    ("email_verification_required", "bool", False, None, None),
    ("referral_required", "bool", False, None, None),
    ("iran_phone_only", "bool", True, None, None),
    ("force_channel_join", "bool", False, None, None),
    ("force_share_phone", "bool", False, None, None),
    ("default_language", "str", "fa", None, None),
    ("product_display_mode", "str", "grouped", None, None),
    ("ios_shortcut_icloud_url", "str", "", None, None),
    # --- Super Admin only (SUPER_ONLY below); each has its own card, not the generic form ---
    # v1.32: deleted users auto-purge (apps/accounts/autopurge.py) — off until a Super Admin turns it on
    ("deleted_purge_enabled", "bool", False, None, None),
    ("deleted_purge_days", "int", 30, 1, 3650),
    # v1.32: Blu collector health (override .env BLU_STALE_MINUTES / BLU_LATE_GRACE_MINUTES; no restart)
    ("blu_ssh_check_minutes", "int", 5, 1, 1440),
    ("blu_stale_minutes", "int", lambda: int(getattr(settings, "BLU_STALE_MINUTES", 360) or 360), 1, 10080),
    ("blu_late_grace_minutes", "int", lambda: int(getattr(settings, "BLU_LATE_GRACE_MINUTES", 30) or 0), 0, 1440),
    # v1.32: rounded-amount auto-approve (apps/payments_sms/rounded.py)
    ("rounded_auto_enabled", "bool", True, None, None),
    ("rounded_max_toman", "int", 2000, 0, 1000000),
    ("rounded_max_percent", "str", "1", None, None),
]
_SPEC = {k: (t, d, lo, hi) for (k, t, d, lo, hi) in EDITABLE_SETTINGS}

# only a Super Admin may change these (403 otherwise, even with settings.manage)
SUPER_ONLY = {"deleted_purge_enabled", "deleted_purge_days", "blu_ssh_check_minutes", "blu_stale_minutes",
              "blu_late_grace_minutes", "rounded_auto_enabled", "rounded_max_toman", "rounded_max_percent"}
# changes to these are audited with old → new values (no personal data in them)
_AUDIT_VALUES = SUPER_ONLY


def _default(d):
    return d() if callable(d) else d


def setting_value(key: str):
    """The current value of an EDITABLE_SETTINGS key (DB row, else its default)."""
    _t, d, _lo, _hi = _SPEC[key]
    return get_setting(key, _default(d))


def _clean_percent(value: str) -> str:
    from decimal import Decimal, InvalidOperation

    try:
        d = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError("rounded_max_percent must be a number (e.g. 1 or 0.5)") from exc
    if not (Decimal("0") <= d <= Decimal("10")) or d.as_tuple().exponent < -2:
        raise ValueError("rounded_max_percent must be between 0 and 10, at most 2 decimals")
    return format(d.normalize(), "f")

# str settings with a validator (returns the cleaned value or raises ValueError)
_VALIDATORS = {
    "ios_shortcut_icloud_url": shortcut.clean_icloud_url,
    "rounded_max_percent": _clean_percent,
}

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
            {"key": k, "type": t, "value": get_setting(k, _default(d)), "min": lo, "max": hi,
             "super_only": k in SUPER_ONLY}
            for (k, t, d, lo, hi) in EDITABLE_SETTINGS
        ]})

    @extend_schema(request=dict, responses=dict, summary="Update runtime settings")
    def put(self, request):
        data = request.data or {}
        locked = sorted(k for k in data if k in SUPER_ONLY)
        if locked and not getattr(request.user, "is_superadmin", False):
            return Response({"detail": f"only a Super Admin can change {', '.join(locked)}",
                             "detail_fa": "فقط سوپرادمین می‌تواند این تنظیمات را تغییر دهد."}, status=403)
        before = {k: setting_value(k) for k in data if k in _AUDIT_VALUES}
        changed = []
        for key, raw in data.items():
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
                    if key in _VALIDATORS:
                        try:
                            val = _VALIDATORS[key](val)
                        except ValueError as exc:
                            return Response({"detail": str(exc), "field": key}, status=400)
            except (TypeError, ValueError):
                return Response({"detail": f"bad value for {key}"}, status=400)
            set_setting(key, val, vtype)
            changed.append(key)
        if changed:
            detail = {"keys": changed}
            values = {k: {"from": before[k], "to": setting_value(k)} for k in changed if k in before}
            if values:
                detail["values"] = values
            write_audit(action="settings.updated", staff=request.user, detail=detail)
            if "blu_ssh_check_minutes" in changed:
                from apps.ops.schedule import reconcile_blu_service_schedule

                reconcile_blu_service_schedule()
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
