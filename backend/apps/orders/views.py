from rest_framework import mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.payments_sms.models import BankCard
from apps.payments_sms.serializers import BankCardSerializer

from .models import Order
from .serializers import OrderCreateSerializer, OrderSerializer


class OrderViewSet(mixins.CreateModelMixin, mixins.ListModelMixin,
                   mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    queryset = Order.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        return (
            Order.objects.filter(user=self.request.user)
            .select_related("plan", "service", "payment")
            .order_by("-created_at")
        )

    def get_serializer_class(self):
        return OrderCreateSerializer if self.action == "create" else OrderSerializer

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data, context={"request": request, "source": "site"})
        ser.is_valid(raise_exception=True)
        order = ser.save()
        reused = bool(getattr(order, "reused", False))
        if reused:
            # re-read so payment_status etc. reflect the existing order
            order = self.get_queryset().get(pk=order.pk)
        body = _checkout_payload(order)
        body["reused"] = reused
        return Response(body, status=200 if reused else 201)

    @action(detail=True, methods=["get"])
    def checkout(self, request, pk=None):
        """Order + payment instructions — lets the invoice page be restored
        after a reload / tab switch (e.g. coming back from the bank app)."""
        return Response(_checkout_payload(self.get_object()))


def _checkout_payload(order: Order) -> dict:
    order_data = OrderSerializer(order).data
    # flowchart 1.2: show the card(s) + the exact amount to pay
    cards = BankCard.objects.filter(is_active=True).order_by("sort_order", "id")
    return {
        "order": order_data,
        "payment_instructions": {
            "amount_to_pay": order_data["amount_unique"],
            "reserved_until": order_data["unique_expire_at"],
            "cards": BankCardSerializer(cards, many=True).data,
        },
    }
