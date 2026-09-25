from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.deletion import RestoreConflict, UserDeletionError, delete_user, restore_conflicts, restore_user
from apps.accounts.models import DeletedUserArchive
from apps.accounts.services import import_legacy_users
from apps.common.models import write_audit
from apps.orders.models import Order

from ..serializers import (
    AdminUserCreateSerializer,
    AdminUserOrderSerializer,
    AdminUserSerializer,
    DeletedUserArchiveDetailSerializer,
    DeletedUserArchiveListSerializer,
    SetPasswordSerializer,
    UserDeleteSerializer,
)
from .base import AdminViewSet
from .finance import _parse_any_date

User = get_user_model()


class UserAdminViewSet(AdminViewSet):
    queryset = User.objects.none()
    perms_map = {"GET": ["users.view"], "*": ["users.manage"]}
    action_perms = {"delete_user": ["users.delete"]}
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["is_active", "source", "language", "is_legacy", "email_verified"]
    search_fields = ["username", "name", "email", "phone", "referral_code", "telegram_username"]
    ordering_fields = ["created_at", "username"]
    ordering = ["-created_at"]

    def get_queryset(self):
        # `referral_count` is a model property; only annotate the non-conflicting one
        qs = User.objects.annotate(service_count=Count("services", distinct=True))
        if self.action == "list":
            # soft-deleted users live in the archive (/admin/deleted-users/); their
            # detail + orders stay reachable by id for the archive's links
            qs = qs.filter(deleted_at__isnull=True)
        return qs

    def perform_update(self, serializer):
        if serializer.instance.deleted_at is not None:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"detail": "deleted users are read-only — restore them first"})
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        # hard delete would cascade into orders/payments and change accounting
        return Response({"detail": "use POST /admin/users/<id>/delete/"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(detail=True, methods=["post"], url_path="delete")
    def delete_user(self, request, pk=None):
        """Soft delete: disable every service on its panel, archive a full
        snapshot, free username/phone/email, revoke sessions, unlink Telegram."""
        user = self.get_object()
        ser = UserDeleteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            archive = delete_user(user, staff=request.user, reason=ser.validated_data["reason"])
        except UserDeletionError as exc:
            code = status.HTTP_502_BAD_GATEWAY if exc.failed else status.HTTP_400_BAD_REQUEST
            return Response({"detail": str(exc), "failed_services": exc.failed}, status=code)
        return Response(DeletedUserArchiveListSerializer(archive).data, status=status.HTTP_200_OK)

    def get_serializer_class(self):
        return AdminUserCreateSerializer if self.action == "create" else AdminUserSerializer

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Per-segment user counts with week-over-week growth. `last_week_count`
        is the size of the same segment as of 7 days ago (by signup date), so
        `growth_*` reflects real cohort growth — no estimates."""
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        base = User.objects.filter(deleted_at__isnull=True)
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

    @action(detail=True, methods=["get"])
    def orders(self, request, pk=None):
        """A user's full order history for the admin purchase-history page —
        based on Order (not Payment) so orders with no payment yet still show."""
        user = self.get_object()
        qs = (
            Order.objects.filter(user=user)
            .select_related("plan", "payment", "payment__confirmed_by_staff")
            .order_by("-created_at")
        )
        return Response(AdminUserOrderSerializer(qs, many=True).data)

    @action(detail=False, methods=["post"], url_path="legacy-import")
    def legacy_import(self, request):
        rows = request.data.get("users", [])
        summary = import_legacy_users(rows, overwrite=bool(request.data.get("overwrite")),
                                     staff=request.user)
        return Response(summary, status=status.HTTP_201_CREATED)


class DeletedUserArchiveViewSet(AdminViewSet):
    """/admin/deleted-users/ — read-only archive of soft-deleted users + restore."""

    queryset = DeletedUserArchive.objects.none()
    http_method_names = ["get", "post", "head", "options"]
    perms_map = {"GET": ["users.view"], "*": ["users.delete"]}
    filter_backends = []

    def get_queryset(self):
        qs = DeletedUserArchive.objects.select_related("user", "deleted_by", "restored_by")
        p = self.request.query_params
        frm = _parse_any_date(p.get("from"))
        to = _parse_any_date(p.get("to"), end_of_day=True)
        if frm:
            qs = qs.filter(deleted_at__gte=frm)
        if to:
            qs = qs.filter(deleted_at__lte=to)
        state = p.get("state")
        if state == "deleted":
            qs = qs.filter(restored_at__isnull=True)
        elif state == "restored":
            qs = qs.filter(restored_at__isnull=False)
        q = (p.get("search") or "").strip().lstrip("@")
        if q:
            match = Q()
            for f in ("original_username", "original_name", "original_phone", "original_email",
                      "original_telegram_username", "reason", "deleted_by_label"):
                match |= Q(**{f"{f}__icontains": q})
            if q.isdigit():
                match |= Q(original_telegram_id=int(q))
            qs = qs.filter(match)
        return qs.order_by("-deleted_at", "-id")

    def get_serializer_class(self):
        return DeletedUserArchiveDetailSerializer if self.action == "retrieve" else DeletedUserArchiveListSerializer

    def create(self, request, *args, **kwargs):
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def retrieve(self, request, *args, **kwargs):
        archive = self.get_object()
        data = DeletedUserArchiveDetailSerializer(archive).data
        can_restore = archive.restored_at is None and archive.user_id is not None and archive.user.deleted_at is not None
        data["restore_conflicts"] = restore_conflicts(archive) if can_restore else {}
        data["can_restore"] = can_restore
        return Response(data)

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        archive = self.get_object()
        try:
            result = restore_user(archive, staff=request.user)
        except RestoreConflict as exc:
            return Response({"detail": str(exc), "conflicts": exc.conflicts}, status=status.HTTP_409_CONFLICT)
        except UserDeletionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            "user_id": result.user.id, "username": result.user.username,
            "telegram_restored": result.telegram_restored, "warnings": result.warnings,
        })
