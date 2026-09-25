"""/admin/apps/ — the operator tools (Android SMS Bridge APK, iPhone Shortcut),
downloaded from our own server so it works on an offline / Iran-only host.

GET    /admin/apps/                        both platforms' current release info
GET    /admin/apps/<platform>/download/    the file (uploaded, or the bundled APK)
                                           ios: built from the repo template, ?device=<id> injects that token
POST   /admin/apps/<platform>/             multipart: file? (android only), version?, link?, notes?, clear_file?

The iPhone Shortcut has ONE source: the repo's mobile_shortcut/CaspinSMS.shortcut
(apps.settings_app.shortcut). It is never uploaded; changing it = edit the repo
file + bump mobile_shortcut/VERSION.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.common.models import write_audit
from apps.payments_sms.models import SmsAppDevice
from apps.settings_app import shortcut
from apps.settings_app.models import AppPlatform, AppRelease

from .base import AdminAPIView

MAX_UPLOAD = 60 * 1024 * 1024
ALLOWED_EXT = {AppPlatform.ANDROID: {".apk"}}   # iOS is built from the repo template, never uploaded


def bundled_apk() -> Path | None:
    """Newest *.apk in APP_RELEASES_DIR (the repo's mobile_sms/release)."""
    d = Path(settings.APP_RELEASES_DIR)
    if not d.is_dir():
        return None
    apks = sorted(d.glob("*.apk"), key=lambda p: p.stat().st_mtime, reverse=True)
    return apks[0] if apks else None


def _info(platform: str) -> dict:
    rel = AppRelease.objects.filter(platform=platform).first()
    out = {
        "platform": platform, "version": "", "link": "", "notes": "", "updated_at": None,
        "updated_by": "", "file_name": "", "size": None, "source": None,
    }
    if rel:
        out.update(version=rel.version, link=rel.link, notes=rel.notes,
                   updated_at=rel.updated_at, updated_by=rel.updated_by)
        if rel.file:
            try:
                out.update(file_name=Path(rel.file.name).name, size=rel.file.size, source="upload")
            except (FileNotFoundError, OSError):
                pass
    if platform == AppPlatform.IOS:
        # the repo template is the only iOS source (an old upload is ignored)
        tpl = shortcut.template_path()
        out.update(file_name="", size=None, source=None, version=out["version"] or "")
        if tpl.is_file():
            st = tpl.stat()
            out.update(file_name=shortcut.TEMPLATE_NAME, size=st.st_size, source="repo",
                       version=shortcut.version() or out["version"],
                       endpoint=shortcut.endpoint_url())
            if not out["updated_at"]:
                out["updated_at"] = timezone.datetime.fromtimestamp(st.st_mtime, tz=timezone.get_current_timezone())
        return out
    if out["source"] is None and platform == AppPlatform.ANDROID:
        apk = bundled_apk()
        if apk:
            st = apk.stat()
            out.update(file_name=apk.name, size=st.st_size, source="bundled")
            if not out["updated_at"]:
                out["updated_at"] = timezone.datetime.fromtimestamp(st.st_mtime, tz=timezone.get_current_timezone())
    return out


class AppReleaseListView(AdminAPIView):
    perms_map = {"GET": ["settings.manage"]}

    @extend_schema(summary="Operator apps (Android SMS bridge, iPhone shortcut) — release info", responses=dict)
    def get(self, request):
        return Response({"results": [_info(p) for p in AppPlatform.values]})


class AppReleaseDetailView(AdminAPIView):
    perms_map = {"POST": ["settings.manage"], "GET": ["settings.manage"]}
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(summary="Upload / update an operator app release", responses=dict)
    def post(self, request, platform):
        if platform not in AppPlatform.values:
            raise Http404
        rel, _ = AppRelease.objects.get_or_create(platform=platform)
        data = request.data
        f = request.FILES.get("file")
        if f is not None and platform == AppPlatform.IOS:
            return Response({"detail": "the iPhone Shortcut is built from the repository (mobile_shortcut/) "
                                       "and cannot be uploaded — update the repo file instead"}, status=400)
        if f is not None:
            ext = Path(f.name).suffix.lower()
            if ext not in ALLOWED_EXT[platform]:
                allowed = ", ".join(sorted(ALLOWED_EXT[platform]))
                return Response({"detail": f"file type must be one of: {allowed}"}, status=400)
            if f.size > MAX_UPLOAD:
                return Response({"detail": "file is too large (max 60 MB)"}, status=400)
            if rel.file:
                rel.file.delete(save=False)
            rel.file.save(f"{platform}{ext}" if platform == AppPlatform.IOS else Path(f.name).name, f, save=False)
        elif str(data.get("clear_file", "")).lower() in ("1", "true", "yes") and rel.file:
            rel.file.delete(save=False)
        for key in ("version", "link", "notes"):
            if key in data:
                setattr(rel, key, (data.get(key) or "").strip())
        if rel.link and not rel.link.startswith(("http://", "https://")):
            return Response({"detail": "link must start with http:// or https://"}, status=400)
        rel.updated_by = getattr(request.user, "username", "")
        rel.save()
        write_audit(action="apps.release_updated", staff=request.user, target=rel,
                    detail={"platform": platform, "version": rel.version, "file": bool(f)})
        return Response(_info(platform))


class AppReleaseDownloadView(AdminAPIView):
    perms_map = {"GET": ["settings.manage"]}

    @extend_schema(summary="Download an operator app from this server", responses=bytes)
    def get(self, request, platform):
        if platform not in AppPlatform.values:
            raise Http404
        if platform == AppPlatform.IOS:
            return self._ios(request)
        rel = AppRelease.objects.filter(platform=platform).first()
        if rel and rel.file:
            name = rel.file.name
            filename = Path(name).name
            ctype = _ctype(filename)
            if getattr(settings, "SERVE_MEDIA_VIA_XACCEL", False):
                resp = HttpResponse(content_type=ctype)
                resp["X-Accel-Redirect"] = f"/_protected_media/{name}"
            else:
                try:
                    resp = FileResponse(rel.file.open("rb"), content_type=ctype)
                except FileNotFoundError as exc:
                    raise Http404 from exc
        elif platform == AppPlatform.ANDROID and (apk := bundled_apk()):
            filename = apk.name
            resp = FileResponse(apk.open("rb"), content_type=_ctype(filename))
        else:
            raise Http404
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        resp["Cache-Control"] = "private, no-store"
        return resp


    def _ios(self, request):
        """Build the shortcut from the repo template: this server's endpoint is
        filled in; ?device=<id> also fills in that device's token (needs
        sms.manage — the same right that can reveal the token in the panel)."""
        if not shortcut.template_path().is_file():
            raise Http404
        token, device = None, None
        device_id = request.query_params.get("device")
        if device_id:
            staff = request.user
            if not (getattr(staff, "is_superadmin", False) or (hasattr(staff, "has_perm") and staff.has_perm("sms.manage"))):
                return Response({"detail": "injecting a device token needs the sms.manage permission"}, status=403)
            device = SmsAppDevice.objects.filter(pk=device_id).first()
            if device is None:
                return Response({"detail": "SMS device not found"}, status=404)
            token = device.api_token
        data = shortcut.build(endpoint=shortcut.endpoint_url(), token=token)
        write_audit(action="apps.shortcut_downloaded", staff=request.user, target=device,
                    detail={"version": shortcut.version(), "device": getattr(device, "id", None)})
        resp = HttpResponse(data, content_type="application/octet-stream")
        resp["Content-Disposition"] = f'attachment; filename="{shortcut.TEMPLATE_NAME}"'
        resp["Cache-Control"] = "private, no-store"
        return resp


def _ctype(filename: str) -> str:
    if filename.endswith(".apk"):
        return "application/vnd.android.package-archive"
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"
