"""v1.53 multi-tenant Phases 10 + 12: store exports (tenancy/export.py) and the monthly store fee (tenancy/fees.py).

Store side (on the store's own domain, `store_ok`): «پشتیبان‌گیری» — status, start, a one-time link. Needs `store.export`
and `Tenant.export_allowed` (checked in export.py). Our side («فروشگاه», never on a store's domain): the same for any store
inside its tenant context, plus the fee settings. The download itself is token-only (no staff JWT: the browser follows the
link), works once, and only on the host the link was made for.
"""
import mimetypes

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .agency import MANAGE, VIEW, _store_or_404
from .base import AdminAPIView

FEE = ["agency.accounting"]


def _err(exc):
    return Response(exc.payload(), status=exc.status)


# ------------------------------------------------------------------ store panel
class StoreExportView(AdminAPIView):
    """GET the store's exports + whether it may make one now · POST start one (built in the background)."""

    perms_map = {"GET": ["store.export"], "POST": ["store.export"]}
    store_ok = True        # only the current store's own exports (TENANT table)

    @extend_schema(responses=dict, summary="The store's own backups («پشتیبان‌گیری»)")
    def get(self, request):
        from apps.tenancy import export

        try:
            return Response(export.status())
        except export.ExportError as exc:
            return _err(exc)

    @extend_schema(request=None, responses=dict, summary="Start a backup of the store's data")
    def post(self, request):
        from apps.tenancy import export

        try:
            e = export.start(staff=request.user)
        except export.ExportError as exc:
            return _err(exc)
        return Response({"export": export.row(e), "message": "Backup started — it is prepared in the background",
                         "message_fa": "ساخت پشتیبان شروع شد — در پس‌زمینه آماده می‌شود"}, status=202)


class StoreExportLinkView(AdminAPIView):
    """POST — a one-time download link for a ready export (a new link ends the previous one)."""

    perms_map = {"POST": ["store.export"]}
    store_ok = True

    @extend_schema(request=None, responses=dict, summary="One-time download link of a backup")
    def post(self, request, pk):
        from apps.tenancy import export

        try:
            return Response(export.link(pk, staff=request.user))
        except export.ExportError as exc:
            return _err(exc)


class StoreExportDownloadView(APIView):
    """GET /api/v1/exports/download/<tenant>/<token>/ — the zip, once. No staff token (a plain browser download): the token is
    the permission, it is spent on first use, and it only works on the host it was made for (store link → that store's
    domain, our staff's link → our host)."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle]

    def get(self, request, tenant_id, token):
        from apps.tenancy import export
        from apps.tenancy.models import Tenant

        try:
            e = export.consume(tenant_id, token)
        except export.ExportError as exc:
            return _err(exc)
        slug = Tenant.objects.filter(pk=tenant_id).values_list("slug", flat=True).first() or "store"
        name = f"{slug}-backup-{e.finished_at:%Y%m%d-%H%M}.zip"
        ctype = mimetypes.types_map.get(".zip", "application/zip")
        if getattr(settings, "SERVE_MEDIA_VIA_XACCEL", False):
            resp = HttpResponse(content_type=ctype)
            resp["X-Accel-Redirect"] = f"/_protected_media/{e.file}"
        else:
            try:
                resp = FileResponse(open(export._path(e.file), "rb"), content_type=ctype)
            except FileNotFoundError as exc:
                raise Http404 from exc
        resp["Content-Disposition"] = f'attachment; filename="{name}"'
        resp["Cache-Control"] = "private, no-store"
        resp["X-Content-Type-Options"] = "nosniff"
        return resp


# ------------------------------------------------------------------ our «فروشگاه» card
class AgencyStoreExportView(AdminAPIView):
    """GET a store's exports · POST start one for it (our staff: no 6-hour gap, export_allowed not needed)."""

    perms_map = {"GET": MANAGE, "POST": MANAGE}

    def get(self, request, username):
        from apps.tenancy import context, export

        t, err = _store_or_404(username)
        if err:
            return err
        with context.tenant_context(t.pk):
            return Response(export.status(platform=True))

    def post(self, request, username):
        from apps.tenancy import context, export

        t, err = _store_or_404(username)
        if err:
            return err
        with context.tenant_context(t.pk):
            try:
                e = export.start(staff=request.user, platform=True)
            except export.ExportError as exc:
                return _err(exc)
            return Response({"export": export.row(e, platform=True), "message": f"Backup of {t.name} started",
                             "message_fa": f"ساخت پشتیبان فروشگاه {t.name} شروع شد"}, status=202)


class AgencyStoreExportLinkView(AdminAPIView):
    perms_map = {"POST": MANAGE}

    def post(self, request, username, pk):
        from apps.tenancy import context, export

        t, err = _store_or_404(username)
        if err:
            return err
        with context.tenant_context(t.pk):
            try:
                return Response(export.link(pk, staff=request.user, platform=True))
            except export.ExportError as exc:
                return _err(exc)


class AgencyStoreFeeView(AdminAPIView):
    """GET / PATCH {enabled, amount, next_due, remind_after_days, suspend_enabled, suspend_after_days} — the monthly store fee
    (off by default; agency.accounting to change it)."""

    perms_map = {"GET": VIEW, "PATCH": FEE}

    def get(self, request, username):
        from apps.tenancy import fees

        t, err = _store_or_404(username)
        if err:
            return err
        return Response({"fee": fees.row(t)})

    def patch(self, request, username):
        from apps.tenancy import fees

        t, err = _store_or_404(username)
        if err:
            return err
        try:
            row = fees.save(t, request.data or {}, staff=request.user)
        except fees.FeeError as exc:
            return Response(exc.payload(), status=exc.status)
        return Response({"fee": row, "message": "Store fee saved", "message_fa": "اشتراک ماهانهٔ فروشگاه ذخیره شد"})
