from rest_framework import mixins, permissions, viewsets

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

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.AllowAny()]
        return [permissions.IsAdminUser()]
