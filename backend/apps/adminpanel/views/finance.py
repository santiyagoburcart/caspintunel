from datetime import timedelta

import jdatetime
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, mixins, viewsets
from rest_framework.response import Response

from apps.common.jalali import to_jalali_str
from apps.payments_sms.models import Payment, PaymentStatus

from ..serializers import TransactionSerializer
from .base import AdminAPIView, _AUTH
from ..permissions import StaffPermission


class TransactionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    authentication_classes = _AUTH
    permission_classes = [StaffPermission]
    perms_map = {"GET": ["payment.view"]}
    queryset = Payment.objects.none()
    serializer_class = TransactionSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["status", "method", "confirmed_by", "bank_card"]
    ordering_fields = ["created_at", "amount"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = Payment.objects.select_related(
            "order", "order__user", "bank_card", "confirmed_by_staff"
        )
        src = self.request.query_params.get("source")
        if src:
            qs = qs.filter(order__source=src)
        return qs.order_by("-created_at")


class AccountingView(AdminAPIView):
    perms_map = {"GET": ["accounting.view"]}

    @extend_schema(
        summary="Revenue report — daily / weekly / monthly / custom range (Jalali)",
        responses=dict,
    )
    def get(self, request):
        period = request.query_params.get("period", "monthly")
        now = timezone.now()

        frm = request.query_params.get("from")
        to = request.query_params.get("to")
        if frm or to:
            start = _parse_any_date(frm) or (now - timedelta(days=30))
            end = _parse_any_date(to, end_of_day=True) or now
        elif period == "daily":
            start, end = now - timedelta(days=1), now
        elif period == "weekly":
            start, end = now - timedelta(days=7), now
        else:
            period, start, end = "monthly", now - timedelta(days=30), now

        approved = Payment.objects.filter(
            status=PaymentStatus.APPROVED, confirmed_at__gte=start, confirmed_at__lte=end
        )

        totals = approved.aggregate(revenue=Sum("amount"), count=Count("id"))
        by_method = list(
            approved.values("method").annotate(revenue=Sum("amount"), count=Count("id"))
        )
        by_source = list(
            approved.values("order__source").annotate(revenue=Sum("amount"), count=Count("id"))
        )
        by_card = list(
            approved.values("bank_card__card_number").annotate(revenue=Sum("amount"), count=Count("id"))
        )
        daily = [
            {
                "date": to_jalali_str(row["day"], "%Y/%m/%d"),
                "date_gregorian": row["day"].isoformat(),
                "revenue": row["revenue"],
                "count": row["count"],
            }
            for row in approved.annotate(day=TruncDate("confirmed_at"))
            .values("day")
            .annotate(revenue=Sum("amount"), count=Count("id"))
            .order_by("day")
        ]

        return Response({
            "period": period,
            "range": {
                "from": to_jalali_str(start, "%Y/%m/%d %H:%M"),
                "to": to_jalali_str(end, "%Y/%m/%d %H:%M"),
                "from_gregorian": start.isoformat(),
                "to_gregorian": end.isoformat(),
            },
            "revenue": totals["revenue"] or 0,
            "transactions": totals["count"] or 0,
            "by_method": by_method,
            "by_source": by_source,
            "by_card": by_card,
            "daily": daily,
        })


def _parse_any_date(value, *, end_of_day=False):
    """Accept an ISO (YYYY-MM-DD) or Jalali (YYYY/MM/DD) date string."""
    if not value:
        return None
    value = value.strip()
    try:
        if "/" in value:  # Jalali YYYY/MM/DD
            y, m, d = (int(x) for x in value.split("/"))
            g = jdatetime.date(y, m, d).togregorian()
            y, m, d = g.year, g.month, g.day
        else:  # Gregorian YYYY-MM-DD
            y, m, d = (int(x) for x in value.split("-"))
        dt = timezone.datetime(y, m, d)
        if end_of_day:
            dt = dt.replace(hour=23, minute=59, second=59)
        return timezone.make_aware(dt)
    except (ValueError, TypeError):
        return None
