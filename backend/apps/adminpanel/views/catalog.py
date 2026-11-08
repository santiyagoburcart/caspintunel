from decimal import Decimal

from django.db.models import Count, Q, Sum
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import Permission, Role, Staff
from apps.payments_sms.models import BankCard, PaymentStatus, SmsAppDevice, SmsSource
from apps.plans.models import Plan
from apps.settings_app.models import Page, Theme

from ..serializers import (
    AdminPlanSerializer,
    AdminBankCardSerializer,
    AdminSmsDeviceSerializer,
    AdminSmsSourceSerializer,
    PageSerializer,
    PermissionSerializer,
    RoleSerializer,
    StaffSerializer,
    ThemeSerializer,
)
from .base import AdminViewSet


class PlanAdminViewSet(AdminViewSet):
    queryset = Plan.objects.all().order_by("sort_order", "id")
    serializer_class = AdminPlanSerializer
    perms_map = {"GET": ["plans.manage"], "*": ["plans.manage"]}
    store_ok = True        # v1.46 (Phase 4): the reseller's own plans and prices (tenant-scoped; tenancy/catalog.py bounds them)

    @action(detail=False, methods=["get"], url_path="store-options")
    def store_options(self, request):
        """Store panel only: the panel and the groups a store plan may use, and whether unlimited plans are allowed."""
        from apps.tenancy import catalog

        try:
            return Response(catalog.options())
        except catalog.CatalogError as exc:
            return Response({"detail": exc.en, "detail_fa": exc.fa}, status=404)


class BankCardViewSet(AdminViewSet):
    queryset = BankCard.objects.none()
    serializer_class = AdminBankCardSerializer
    perms_map = {"GET": ["payment.view"], "*": ["settings.manage"]}
    store_ok = True        # v1.47 (Phase 5): the store's own receiving cards

    def get_queryset(self):
        approved = Q(payments__status=PaymentStatus.APPROVED, payments__voided_at__isnull=True)
        return (
            BankCard.objects.annotate(
                deposit_total=Sum("payments__amount", filter=approved),
                deposit_count=Count("payments", filter=approved),
            )
            .order_by("sort_order", "id")
        )

    @action(detail=False, methods=["get"], url_path="deposit-report")
    def deposit_report(self, request):
        rows = self.get_queryset()
        data = AdminBankCardSerializer(rows, many=True).data
        total = sum((Decimal(r["deposit_total"] or 0) for r in data), Decimal(0))
        return Response({"cards": data, "grand_total": total})


class SmsSourceViewSet(AdminViewSet):
    """The bank sender numbers allowed to auto-confirm deposits (see
    apps.payments_sms.matching._resolve_source)."""

    queryset = SmsSource.objects.all().order_by("-created_at")
    serializer_class = AdminSmsSourceSerializer
    perms_map = {"GET": ["sms.manage"], "*": ["sms.manage"]}
    store_ok = True        # v1.47 (Phase 5): the store's own bank sender numbers


class SmsAppDeviceViewSet(AdminViewSet):
    """The Android SMS-forwarding app's device tokens (see mobile_sms/).
    List/patch/delete only ever expose the masked tail — the real token is
    returned once on create, and again on demand via the `token` action."""

    queryset = SmsAppDevice.objects.all().order_by("-created_at")
    serializer_class = AdminSmsDeviceSerializer
    perms_map = {"GET": ["sms.manage"], "*": ["sms.manage"]}
    store_ok = True        # v1.47 (Phase 5): the store's own SMS devices + tokens

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        data = dict(serializer.data)
        data["api_token"] = serializer.instance.api_token
        headers = self.get_success_headers(serializer.data)
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=["get"], url_path="token")
    def token(self, request, pk=None):
        device = self.get_object()
        return Response({"api_token": device.api_token})


class PageViewSet(AdminViewSet):
    queryset = Page.objects.all().order_by("slug")
    serializer_class = PageSerializer
    perms_map = {"GET": ["pages.manage"], "*": ["pages.manage"]}
    store_ok = True                      # v1.43: pages are per store (tenant-scoped)


class ThemeViewSet(AdminViewSet):
    """Themes. v1.43 on a store's domain: the built-in themes (read-only there) + the store's own; «فعال‌سازی» sets the
    store's theme (TenantBranding.theme) — the global active flag is our own store's."""

    queryset = Theme.objects.all().order_by("name")
    serializer_class = ThemeSerializer
    perms_map = {"GET": ["themes.manage"], "*": ["themes.manage"]}
    store_ok = True

    def get_queryset(self):
        from django.db.models import Q

        from apps.settings_app.branding import current_tenant_id

        # built-in themes + the current tenant's own (never another store's)
        return super().get_queryset().filter(Q(tenant__isnull=True) | Q(tenant_id=current_tenant_id()))

    def list(self, request, *args, **kwargs):
        """On a store's domain «فعال» = the store's theme (TenantBranding.theme, else the first built-in)."""
        from apps.settings_app.branding import is_store, store_branding

        resp = super().list(request, *args, **kwargs)
        if is_store():
            b = store_branding()
            active = b.theme_id or Theme.objects.filter(tenant__isnull=True).order_by("id").values_list("id", flat=True).first()
            rows = resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data
            for r in rows:
                r["is_active"] = r["id"] == active
        return resp

    def perform_create(self, serializer):
        from apps.settings_app.branding import current_tenant_id, is_store

        serializer.save(**({"tenant_id": current_tenant_id(), "is_active": False} if is_store() else {}))

    def _own_only(self, theme):
        from rest_framework.exceptions import PermissionDenied

        from apps.settings_app.branding import is_store

        if is_store() and theme.tenant_id is None:
            raise PermissionDenied("a built-in theme can't be changed from a store — copy it as a new theme")

    def perform_update(self, serializer):
        self._own_only(serializer.instance)
        from apps.settings_app.branding import is_store

        serializer.save(**({"is_active": False} if is_store() else {}))

    def perform_destroy(self, instance):
        self._own_only(instance)
        instance.delete()

    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, pk=None):
        from apps.settings_app.branding import is_store, store_branding

        theme = self.get_object()
        if is_store():
            b = store_branding()
            b.theme = theme
            b.save(update_fields=["theme", "updated_at"])
            return Response({**ThemeSerializer(theme).data, "is_active": True})
        theme.is_active = True
        theme.save()  # model.save() deactivates the others
        return Response(ThemeSerializer(theme).data)


class RoleViewSet(AdminViewSet):
    queryset = Role.objects.prefetch_related("permissions").order_by("name")
    serializer_class = RoleSerializer
    perms_map = {"GET": ["roles.manage"], "*": ["roles.manage"]}


class PermissionListViewSet(AdminViewSet):
    queryset = Permission.objects.all().order_by("code")
    serializer_class = PermissionSerializer
    http_method_names = ["get"]
    perms_map = {"GET": ["roles.manage"]}


class StaffViewSet(AdminViewSet):
    queryset = Staff.objects.select_related("role", "group_manager").order_by("username")
    serializer_class = StaffSerializer
    perms_map = {"GET": ["roles.manage"], "*": ["roles.manage"]}
    filter_backends = [filters.SearchFilter]
    search_fields = ["username"]

    @action(detail=False, methods=["get"], url_path="group-manager-options")
    def group_manager_options(self, request):
        """Agency groups + PasarGuard roles for a "Group manager" staff (v1.25.2)."""
        from apps.agency.managers import options_payload

        return Response(options_payload())
