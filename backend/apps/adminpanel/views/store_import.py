"""v1.56 «ورود داده از ربات قبلی» on our «فروشگاه» card (apps/tenancy/importers, docs/store-import.md).

OUR staff only (`agency.manage`), never on a store's domain (no `store_ok`). Every call runs inside the store's tenant
context. Upload → background scan (preview) → run (with «ربات قبلی فروش را متوقف کرده است») → optional undo. The CSV
report lists every service and customer with what happened to it (for the reseller to check).
"""
from django.http import HttpResponse
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from .agency import MANAGE, _store_or_404
from .base import AdminAPIView


def _err(exc):
    return Response(exc.payload(), status=exc.status)


class AgencyStoreImportsView(AdminAPIView):
    """GET the store's imports (the newest with its preview) · POST (multipart `file`) upload a dump → scan starts."""

    perms_map = {"GET": MANAGE, "POST": MANAGE}
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request, username):
        from apps.tenancy import context
        from apps.tenancy.importers import engine

        t, err = _store_or_404(username)
        if err:
            return err
        with context.tenant_context(t.pk):
            try:
                return Response(engine.status())
            except engine.ImportFailure as exc:
                return _err(exc)

    def post(self, request, username):
        from apps.tenancy import context
        from apps.tenancy.importers import dump, engine

        t, err = _store_or_404(username)
        if err:
            return err
        f = request.FILES.get("file")
        if f is None:
            return Response({"detail": "choose a file", "detail_fa": "یک فایل انتخاب کنید", "code": "no_file"}, status=400)
        raw = f.read(dump.MAX_UPLOAD + 1)
        with context.tenant_context(t.pk):
            try:
                obj = engine.upload(raw, f.name, staff=request.user)
            except engine.ImportFailure as exc:
                return _err(exc)
            return Response({"import": engine.row(obj), "message": "File received — reading it",
                             "message_fa": "فایل دریافت شد — در حال بررسی"}, status=202)


class AgencyStoreImportView(AdminAPIView):
    """GET one import with its preview · DELETE discard it (deletes the uploaded file; not after it ran)."""

    perms_map = {"GET": MANAGE, "DELETE": MANAGE}

    def get(self, request, username, pk):
        from apps.tenancy import context
        from apps.tenancy.importers import engine
        from apps.tenancy.models import StoreImport

        t, err = _store_or_404(username)
        if err:
            return err
        with context.tenant_context(t.pk):
            obj = StoreImport.objects.filter(pk=pk).first()
            if obj is None:
                return Response({"detail": "not found", "detail_fa": "پیدا نشد"}, status=404)
            return Response(engine.row(obj, full=True))

    def delete(self, request, username, pk):
        from apps.tenancy import context
        from apps.tenancy.importers import engine

        t, err = _store_or_404(username)
        if err:
            return err
        with context.tenant_context(t.pk):
            try:
                engine.discard(pk, staff=request.user)
            except engine.ImportFailure as exc:
                return _err(exc)
        return Response({"message": "Discarded", "message_fa": "کنار گذاشته شد"})


class AgencyStoreImportRunView(AdminAPIView):
    """POST {old_bot_stopped: true, plan_map, confirm_credits, credit_days} → the import runs in the background."""

    perms_map = {"POST": MANAGE}

    def post(self, request, username, pk):
        from apps.tenancy import context
        from apps.tenancy.importers import engine

        t, err = _store_or_404(username)
        if err:
            return err
        with context.tenant_context(t.pk):
            try:
                obj = engine.start(pk, request.data or {}, staff=request.user)
            except engine.ImportFailure as exc:
                return _err(exc)
            return Response({"import": engine.row(obj), "message": "Import started", "message_fa": "ورود داده شروع شد"},
                            status=202)


class AgencyStoreImportUndoView(AdminAPIView):
    perms_map = {"POST": MANAGE}

    def post(self, request, username, pk):
        from apps.tenancy import context
        from apps.tenancy.importers import engine

        t, err = _store_or_404(username)
        if err:
            return err
        with context.tenant_context(t.pk):
            try:
                out = engine.undo(pk, staff=request.user)
            except engine.ImportFailure as exc:
                return _err(exc)
        return Response({**out, "message": "Import undone", "message_fa": "ورود داده بازگردانده شد"})


class AgencyStoreImportReportView(AdminAPIView):
    """GET the CSV report (UTF-8 with BOM — opens in Excel)."""

    perms_map = {"GET": MANAGE}

    def get(self, request, username, pk):
        from apps.tenancy import context
        from apps.tenancy.importers import engine

        t, err = _store_or_404(username)
        if err:
            return err
        with context.tenant_context(t.pk):
            try:
                name, body = engine.report_csv(pk)
            except engine.ImportFailure as exc:
                return _err(exc)
        resp = HttpResponse(body, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{name}"'
        resp["Cache-Control"] = "no-store"
        return resp
