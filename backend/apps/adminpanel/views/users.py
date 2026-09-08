from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.services import import_legacy_users
from apps.common.models import write_audit

from ..serializers import AdminUserCreateSerializer, AdminUserSerializer, SetPasswordSerializer
from .base import AdminViewSet

User = get_user_model()


class UserAdminViewSet(AdminViewSet):
    queryset = User.objects.none()
    perms_map = {"GET": ["users.view"], "*": ["users.manage"]}
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["is_active", "source", "language", "is_legacy", "email_verified"]
    search_fields = ["username", "name", "email", "phone", "referral_code", "telegram_username"]
    ordering_fields = ["created_at", "username"]
    ordering = ["-created_at"]

    def get_queryset(self):
        # `referral_count` is a model property; only annotate the non-conflicting one
        return User.objects.annotate(service_count=Count("services", distinct=True))

    def get_serializer_class(self):
        return AdminUserCreateSerializer if self.action == "create" else AdminUserSerializer

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Per-segment user counts with week-over-week growth. `last_week_count`
        is the size of the same segment as of 7 days ago (by signup date), so
        `growth_*` reflects real cohort growth — no estimates."""
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        base = User.objects.all()
        segments = {
            "total": base,
            "active": base.filter(is_active=True),
            "bot": base.filter(source="bot"),
            "site": base.filter(source="site"),
        }
        out = {}
        for key, qs in segments.items():
            count = qs.count()
            last_week = qs.filter(created_at__lt=week_ago).count()
            diff = count - last_week
            if last_week:
                pct = round(diff / last_week * 100, 1)
            else:
                pct = 100.0 if diff > 0 else 0.0
            out[key] = {
                "count": count,
                "last_week_count": last_week,
                "growth_percent": pct,
                "growth_direction": "up" if diff > 0 else ("down" if diff < 0 else "flat"),
            }
        return Response(out)

    @action(detail=True, methods=["post"], url_path="set-password")
    def set_password(self, request, pk=None):
        user = self.get_object()
        ser = SetPasswordSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user.set_password(ser.validated_data["password"])
        user.save(update_fields=["password", "updated_at"])
        write_audit(action="user.password_set_by_staff", target=user, staff=request.user)
        return Response({"detail": "password updated"})

    @action(detail=True, methods=["post"])
    def disable(self, request, pk=None):
        return self._toggle(request, active=False)

    @action(detail=True, methods=["post"])
    def enable(self, request, pk=None):
        return self._toggle(request, active=True)

    def _toggle(self, request, *, active):
        user = self.get_object()
        user.is_active = active
        user.save(update_fields=["is_active", "updated_at"])
        write_audit(action=f"user.{'enabled' if active else 'disabled'}", target=user, staff=request.user)
        return Response({"id": user.id, "is_active": user.is_active})

    @action(detail=False, methods=["post"], url_path="legacy-import")
    def legacy_import(self, request):
        rows = request.data.get("users", [])
        summary = import_legacy_users(rows, overwrite=bool(request.data.get("overwrite")),
                                     staff=request.user)
        return Response(summary, status=status.HTTP_201_CREATED)
