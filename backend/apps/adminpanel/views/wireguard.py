"""v1.55 «مکان‌های وایرگارد» (panel/wireguard.py): country name + flag per WireGuard location code — our staff only."""
from rest_framework import serializers

from apps.common.models import write_audit
from apps.panel.models import WireguardLocation

from rest_framework.response import Response

from .base import AdminAPIView, AdminViewSet


class WireguardLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = WireguardLocation
        fields = ("id", "code", "name_fa", "name_en", "flag", "slug", "sort_order", "is_active", "updated_at")

    def validate_code(self, v):
        v = (v or "").strip()
        qs = WireguardLocation.objects.filter(code__iexact=v)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("این کد قبلاً ثبت شده است")
        return v

    def validate_slug(self, v):
        """v1.55.2 «نام فایل» = the WireGuard tunnel name (with the global template): ≤ 15 of A-Z a-z 0-9 _ = + . -"""
        from apps.panel import wireguard as W

        v = (v or "").strip()
        if v.lower().endswith(".conf"):
            v = v[:-5]
        why = W.tunnel_problem(v)
        if why:
            raise serializers.ValidationError(why)
        qs = WireguardLocation.objects.filter(slug__iexact=v)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("این نام فایل برای مکان دیگری ثبت شده است")
        why = W.tunnel_problem(W.render(W.template(), v, _sample_service_id()))
        if why:
            raise serializers.ValidationError(f"با الگوی فعلی: {why}")
        return v


def _sample_service_id() -> int:
    from django.db.models import Max

    from apps.panel.models import Service

    top = Service.objects.aggregate(m=Max("id"))["m"] or 0      # ids are global; this store's newest is close enough
    return max(int(top) * 10, 9999)                        # room for the next numbers (× 10)


class WireguardLocationViewSet(AdminViewSet):
    queryset = WireguardLocation.objects.all()
    serializer_class = WireguardLocationSerializer
    perms_map = {"GET": ["plans.manage"], "*": ["settings.manage"]}
    pagination_class = None

    def perform_create(self, serializer):
        obj = serializer.save()
        write_audit(action="wireguard.location_created", staff=self.request.user, target=obj, detail=serializer.data)

    def perform_update(self, serializer):
        obj = serializer.save()
        write_audit(action="wireguard.location_updated", staff=self.request.user, target=obj, detail=serializer.data)

    def perform_destroy(self, instance):
        write_audit(action="wireguard.location_deleted", staff=self.request.user, target=instance, detail={"code": instance.code})
        instance.delete()


class WireguardTemplateView(AdminAPIView):
    """GET / PUT {template} — the global name template of the .conf files (default "{location}"); the answer carries a preview
    of every location's tunnel name."""

    perms_map = {"GET": ["plans.manage"], "PUT": ["settings.manage"]}

    def _payload(self, tpl):
        from apps.panel import wireguard as W

        sid = _sample_service_id()
        locs = list(WireguardLocation.objects.filter(is_active=True).values_list("code", "slug"))
        return {"template": tpl, "default": W.DEFAULT_TEMPLATE, "sample_service": sid,
                "preview": [{"code": c, "name": W.render(tpl, s or c, sid), "problem": W.tunnel_problem(W.render(tpl, s or c, sid))}
                            for c, s in locs]}

    def get(self, request):
        from apps.panel import wireguard as W

        return Response(self._payload(W.template()))

    def put(self, request):
        from apps.panel import wireguard as W
        from apps.settings_app.models import ValueType
        from apps.settings_app.utils import set_setting

        tpl = str((request.data or {}).get("template") or "").strip() or W.DEFAULT_TEMPLATE
        slugs = [s or c for c, s in WireguardLocation.objects.filter(is_active=True).values_list("code", "slug")]
        why = W.template_problem(tpl, slugs, _sample_service_id())
        if why:
            return Response({"detail": why, "detail_fa": why, "field": "template"}, status=400)
        set_setting(W.TEMPLATE_KEY, tpl, ValueType.STR)
        write_audit(action="wireguard.template_updated", staff=request.user, target=None, detail={"template": tpl})
        return Response({**self._payload(tpl), "message": "Saved", "message_fa": "الگوی نام فایل ذخیره شد"})
