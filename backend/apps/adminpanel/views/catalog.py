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
        except Exception as exc:  # noqa: BLE001 — v1.52: no agency panel configured / reachable → 503, never a 500
            return Response({"detail": f"the agency panel is not available: {exc}"[:300],
                             "detail_fa": "پنل نمایندگی در دسترس نیست — بعداً دوباره امتحان کنید"}, status=503)


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

    @action(detail=True, methods=["get"], url_path="setup-code")
    def setup_code(self, request, pk=None):
        """v1.60 «کد راه‌اندازی»: one string (this store's address + the device token) pasted once into the Android app."""
        from apps.payments_sms.device_url import server_base, setup_code

        device = self.get_object()
        base = server_base(request)
        return Response({"code": setup_code(base, device.api_token), "server": base, "device": device.name})


class PageViewSet(AdminViewSet):
    queryset = Page.objects.all().order_by("slug")
    serializer_class = PageSerializer
    perms_map = {"GET": ["pages.manage"], "*": ["pages.manage"]}
    store_ok = True                      # v1.43: pages are per store (tenant-scoped)


class ThemeViewSet(AdminViewSet):
    """Themes — OUR panel only. v1.60: stores never manage themes (not store_ok, `themes.manage` is not a store code); a
    store shows our active theme or the override our staff set on «فروشگاه» (settings_app/themes.py)."""

    queryset = Theme.objects.all().order_by("name")
    serializer_class = ThemeSerializer
    perms_map = {"GET": ["themes.manage"], "*": ["themes.manage"]}

    def get_queryset(self):
        from apps.settings_app.themes import our_themes

        return our_themes()

    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, pk=None):
        theme = self.get_object()
        theme.is_active = True
        theme.save()  # model.save() deactivates the others; every store that follows ours switches with it
        return Response(ThemeSerializer(theme).data)


def _here():
    """The current store (None = ours). v1.52: roles / staff are listed and edited only inside their own store."""
    from apps.tenancy.context import store_id

    return store_id()


class RoleViewSet(AdminViewSet):
    queryset = Role.objects.none()
    serializer_class = RoleSerializer
    perms_map = {"GET": ["roles.manage"], "*": ["roles.manage"]}
    store_ok = True        # v1.52 (Phase 8): a store's own roles, codes ⊆ its ceiling (tenancy/staff.py)

    def get_queryset(self):
        return Role.objects.filter(tenant_id=_here()).prefetch_related("permissions").order_by("name")

    def perform_destroy(self, instance):
        from apps.tenancy.staff import OWNER_ROLE

        if instance.tenant_id and instance.name == OWNER_ROLE:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("the store owner's role is managed by us (it follows the store's ceiling)")
        instance.delete()


class PermissionListViewSet(AdminViewSet):
    queryset = Permission.objects.none()
    serializer_class = PermissionSerializer
    http_method_names = ["get"]
    perms_map = {"GET": ["roles.manage"]}
    store_ok = True        # v1.52: on a store's panel only what that store may grant

    def get_queryset(self):
        qs = Permission.objects.all().order_by("code")
        if _here():
            from apps.tenancy.staff import grantable

            qs = qs.filter(code__in=list(grantable(self.request.user)))
        return qs


class StaffViewSet(AdminViewSet):
    queryset = Staff.objects.none()
    serializer_class = StaffSerializer
    perms_map = {"GET": ["roles.manage"], "*": ["roles.manage"]}
    filter_backends = [filters.SearchFilter]
    search_fields = ["username"]
    store_ok = True        # v1.52 (Phase 8): a store's own staff only; ours never listed there, a store's never here

    def get_queryset(self):
        return Staff.objects.filter(tenant_id=_here()).select_related("role", "group_manager").order_by("username")

    def perform_destroy(self, instance):
        from apps.tenancy.staff import OWNER_ROLE

        if instance.tenant_id and instance.role_id and instance.role.name == OWNER_ROLE:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("the store owner's account is managed by us on «فروشگاه»")
        from apps.agency.models import GroupManager

        gm = GroupManager.objects.filter(staff=instance).first()
        if gm is not None:
            # v1.54: a group manager's account is never deleted — the manager is deactivated + archived (its requests,
            # payments, notices and activity stay; its groups pay directly again) and the login is switched off
            from apps.agency.archive import deactivate_manager
            from apps.common.models import write_audit

            deactivate_manager(gm, by=getattr(self.request.user, "username", ""))
            instance.is_active = False
            instance.token_version = (instance.token_version or 0) + 1           # ends every session of the account
            instance.save(update_fields=["is_active", "token_version", "updated_at"])
            write_audit(action="staff.deactivated_group_manager", staff=self.request.user, target=instance,
                        detail={"staff": instance.username, "manager": gm.username})
            return
        instance.delete()

    @action(detail=False, methods=["get"], url_path="group-manager-options")
    def group_manager_options(self, request):
        """Agency groups + PasarGuard roles for a "Group manager" staff (v1.25.2)."""
        if _here():
            from django.http import Http404

            raise Http404           # v1.52: agency data is ours — never on a store's panel
        from apps.agency.managers import options_payload

        return Response(options_payload())
