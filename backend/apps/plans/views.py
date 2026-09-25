from rest_framework import permissions, viewsets
from rest_framework.throttling import ScopedRateThrottle

from apps.common.public_cache import cached_public

from .models import Plan
from .serializers import PlanSerializer, PlanWriteSerializer


class PlanViewSet(viewsets.ModelViewSet):
    """
    Customers: list/retrieve active plans.
    Admins (is_staff): full CRUD.
    """

    queryset = Plan.objects.all()

    def get_queryset(self):
        qs = Plan.objects.all().order_by("sort_order", "id")
        if not (self.request.user.is_authenticated and self.request.user.is_staff):
            qs = qs.filter(is_active=True)
        return qs

    def get_serializer_class(self):
        if self.action in ("list", "retrieve"):
            return PlanSerializer
        return PlanWriteSerializer

    def _public(self):
        return self.action in ("list", "retrieve") and not (
            self.request.user.is_authenticated and self.request.user.is_staff)

    def get_throttles(self):
        # the public catalog is a cheap cached read: "public_read" scope
        if self._public():
            self.throttle_scope = "public_read"
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def list(self, request, *args, **kwargs):
        if self._public():
            return cached_public(request, "plans", lambda: super(PlanViewSet, self).list(request, *args, **kwargs))
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        if self._public():
            return cached_public(request, "plan", lambda: super(PlanViewSet, self).retrieve(request, *args, **kwargs))
        return super().retrieve(request, *args, **kwargs)

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.AllowAny()]
        return [permissions.IsAdminUser()]
