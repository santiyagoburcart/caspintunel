from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.common import qrcard
from apps.common.models import write_audit
from apps.settings_app.models import SiteConfig

from ..serializers import SiteConfigSerializer, TenantBrandingSerializer
from .base import AdminAPIView


@extend_schema(request=SiteConfigSerializer, responses=SiteConfigSerializer)
class SiteConfigView(AdminAPIView):
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    serializer_class = SiteConfigSerializer
    perms_map = {"GET": ["settings.manage"], "PUT": ["settings.manage"], "PATCH": ["settings.manage"]}

    store_ok = True                      # v1.43: on a store's domain it edits that store's branding

    @staticmethod
    def _target():
        from apps.settings_app.branding import is_store, store_branding

        return (store_branding(), TenantBrandingSerializer) if is_store() else (SiteConfig.load(), SiteConfigSerializer)

    def get(self, request):
        obj, ser = self._target()
        return Response(ser(obj, context={"request": request}).data)

    def put(self, request):
        return self._save(request, partial=False)

    def patch(self, request):
        return self._save(request, partial=True)

    def _save(self, request, *, partial):
        cfg, cls = self._target()
        if "theme" in request.data and cls is TenantBrandingSerializer:
            from apps.settings_app.models import Theme

            tid = request.data.get("theme")
            if tid and not Theme.objects.filter(pk=tid).filter(_own_or_builtin()).exists():
                return Response({"theme": ["not one of this store's themes"]}, status=400)
        ser = cls(cfg, data=request.data, partial=partial, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        write_audit(action="branding.updated", target=cfg, staff=request.user,
                    detail={"fields": list(request.data.keys())})
        return Response(ser.data)


class QrPreviewView(AdminAPIView):
    """A sample QR on a background: `?bg=<key>` (default: the active one),
    `?size=` 160–1080 for picker thumbnails."""

    perms_map = {"GET": ["settings.manage"]}
    store_ok = True

    @extend_schema(summary="Sample subscription QR on a background (PNG)", responses=bytes)
    def get(self, request):
        from apps.settings_app.branding import branding

        cfg = branding()
        key = request.query_params.get("bg") or cfg.qr_background or qrcard.DEFAULT
        if key not in qrcard.CHOICES:
            key = qrcard.DEFAULT
        try:
            size = min(max(int(request.query_params.get("size", qrcard.SIZE)), 160), qrcard.SIZE)
        except ValueError:
            size = qrcard.SIZE
        bg = qrcard.background_image(key, cfg.qr_background_custom, size)
        img, _ = qrcard.compose("https://example.com/sub/sample-subscription-link", bg, size)
        resp = HttpResponse(qrcard.to_png(img), content_type="image/png")
        resp["Cache-Control"] = "private, no-store"
        return resp


def _own_or_builtin():
    """Themes a store may use: the built-in ones (tenant NULL) and its own."""
    from django.db.models import Q

    from apps.settings_app.branding import current_tenant_id

    return Q(tenant__isnull=True) | Q(tenant_id=current_tenant_id())
