from drf_spectacular.utils import extend_schema
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.common.models import write_audit
from apps.settings_app.models import SiteConfig

from ..serializers import SiteConfigSerializer
from .base import AdminAPIView


@extend_schema(request=SiteConfigSerializer, responses=SiteConfigSerializer)
class SiteConfigView(AdminAPIView):
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    serializer_class = SiteConfigSerializer
    perms_map = {"GET": ["settings.manage"], "PUT": ["settings.manage"], "PATCH": ["settings.manage"]}

    def get(self, request):
        return Response(SiteConfigSerializer(SiteConfig.load(), context={"request": request}).data)

    def put(self, request):
        return self._save(request, partial=False)

    def patch(self, request):
        return self._save(request, partial=True)

    def _save(self, request, *, partial):
        cfg = SiteConfig.load()
        ser = SiteConfigSerializer(cfg, data=request.data, partial=partial, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        write_audit(action="branding.updated", target=cfg, staff=request.user,
                    detail={"fields": list(request.data.keys())})
        return Response(ser.data)
