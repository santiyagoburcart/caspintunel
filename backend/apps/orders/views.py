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

    @action(detail=False, methods=["post"], url_path="quote")
    def quote(self, request):
        """v1.26: the price before payment — original, discount, final — for the
        purchase in the body (same fields as create) and an optional discount code.
        A refused code answers 400 with the reason (Persian / English) + discount_error."""
        from .services import DiscountCodeRefused, OrderError, RenewalWaiting, quote_order

        d = request.data
        lang = "en" if d.get("lang") == "en" else "fa"
        try:
            q = quote_order(user=request.user, plan_id=d.get("plan"), order_type=d.get("type") or "new",
                            custom_volume_gb=d.get("custom_volume_gb") or None, service_id=d.get("service") or None,
                            discount_code=(d.get("discount_code") or "").strip() or None)
        except DiscountCodeRefused as exc:
            return Response({"discount_code": [exc.message(lang)], "discount_error": exc.code}, status=400)
        except RenewalWaiting as exc:
            return Response({"detail": exc.message(lang), "code": exc.code}, status=409)
        except (OrderError, ValueError, TypeError) as exc:
            return Response({"detail": str(exc)}, status=400)
        from decimal import Decimal

        return Response({k: (str(v) if isinstance(v, Decimal) else v) for k, v in q.items()})

    @action(detail=True, methods=["post"], url_path="account-name")
    def account_name(self, request, pk=None):
        """Paid order whose name exists on the panel: the customer's new name → fulfilment again."""
        from .services import OrderError, rename_paid_order

        try:
            order = rename_paid_order(self.get_object(), request.data.get("requested_account_name") or "")
        except OrderError as exc:
            return Response({"requested_account_name": [str(exc)]}, status=400)
        return Response(_checkout_payload(order))

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
