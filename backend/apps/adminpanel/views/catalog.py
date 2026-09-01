from decimal import Decimal

from django.db.models import Count, Q, Sum
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import Permission, Role, Staff
from apps.payments_sms.models import BankCard, PaymentStatus
from apps.plans.models import Plan
from apps.settings_app.models import Page, Theme

from ..serializers import (
    AdminPlanSerializer,
    AdminBankCardSerializer,
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


class BankCardViewSet(AdminViewSet):
    queryset = BankCard.objects.none()
    serializer_class = AdminBankCardSerializer
    perms_map = {"GET": ["payment.view"], "*": ["settings.manage"]}

    def get_queryset(self):
        approved = Q(payments__status=PaymentStatus.APPROVED)
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


class PageViewSet(AdminViewSet):
    queryset = Page.objects.all().order_by("slug")
    serializer_class = PageSerializer
    perms_map = {"GET": ["pages.manage"], "*": ["pages.manage"]}


class ThemeViewSet(AdminViewSet):
    queryset = Theme.objects.all().order_by("name")
    serializer_class = ThemeSerializer
    perms_map = {"GET": ["themes.manage"], "*": ["themes.manage"]}

    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, pk=None):
        theme = self.get_object()
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
    queryset = Staff.objects.select_related("role").order_by("username")
    serializer_class = StaffSerializer
    perms_map = {"GET": ["roles.manage"], "*": ["roles.manage"]}
    filter_backends = [filters.SearchFilter]
    search_fields = ["username"]
