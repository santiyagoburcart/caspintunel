"""v1.55 «مکان‌های وایرگارد» (panel/wireguard.py): country name + flag per WireGuard location code — our staff only."""
from rest_framework import serializers

from apps.common.models import write_audit
from apps.panel.models import WireguardLocation

from .base import AdminViewSet


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
        import re

        return re.sub(r"[^a-z0-9-]+", "-", (v or "").lower()).strip("-")[:24]


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
