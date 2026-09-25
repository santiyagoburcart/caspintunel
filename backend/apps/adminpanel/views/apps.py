"""/admin/apps/ — the operator tools (Android SMS Bridge APK, iPhone Shortcut),
downloaded from our own server so it works on an offline / Iran-only host.

GET    /admin/apps/                        both platforms' current release info
GET    /admin/apps/<platform>/download/    the file (uploaded, or the bundled APK)
POST   /admin/apps/<platform>/             multipart: file?, version?, link?, notes?, clear_file?
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
from apps.settings_app.models import AppPlatform, AppRelease

from .base import AdminAPIView

MAX_UPLOAD = 60 * 1024 * 1024
ALLOWED_EXT = {AppPlatform.ANDROID: {".apk"}, AppPlatform.IOS: {".shortcut", ".plist", ".zip"}}


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


def _ctype(filename: str) -> str:
    if filename.endswith(".apk"):
        return "application/vnd.android.package-archive"
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"
