import logging

from django.http import HttpResponse
from rest_framework import mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.common.qrcard import qr_card_png

from .exceptions import PanelError
from .models import Service
from .serializers import ServiceSerializer
from .services import refresh_watchable_services, revoke_subscription, sync_service

log = logging.getLogger("caspintunel")


class WireguardThrottle(UserRateThrottle):
    """v1.55: WireGuard downloads per account (each one asks PasarGuard)."""
    scope = "wireguard"


class ServiceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ServiceSerializer
    queryset = Service.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Service.objects.none()
        return (
            Service.objects.filter(user=self.request.user)
            .select_related("current_plan", "panel")
            .order_by("-created_at")
        )

    def list(self, request, *args, **kwargs):
        # silent, on every load/poll — on_hold flips to active here without any
        # user action (throttled + capped in refresh_watchable_services)
        refresh_watchable_services(list(self.get_queryset()))
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        refresh_watchable_services([self.get_object()])
        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="refresh")
    def refresh(self, request, pk=None):
        """Optional manual force-sync (the list/detail already auto-syncs)."""
        service = self.get_object()
        try:
            sync_service(service.id)
        except PanelError as exc:
            return Response({"detail": str(exc)}, status=502)
        service.refresh_from_db()
        return Response(self.get_serializer(service).data)

    @action(detail=True, methods=["post"], url_path="revoke")
    def revoke(self, request, pk=None):
        """Regenerate the subscription link — disconnects every device using
        the old one. The frontend shows a confirmation warning before calling this."""
        service = self.get_object()
        try:
            revoke_subscription(service.id)
        except PanelError as exc:
            return Response({"detail": str(exc)}, status=502)
        service.refresh_from_db()
        return Response(self.get_serializer(service).data)

    @action(detail=True, methods=["get"], url_path="renew-info")
    def renew_info(self, request, pk=None):
        """How this service can be renewed — always on the SAME PasarGuard account and
        subscription link. `plan` = its own plan when that can be bought again (one-tap
        renewal); `plans` = every plan it may switch / upgrade to. A service without a
        usable plan (e.g. linked manually by staff) has `plan: null, needs_plan: true`. v1.42.1: custom-volume plans
        renew too — `last_gb` pre-fills the volume (the last one bought for this service, else its current volume)."""
        from apps.orders.services import (
            RenewalWaiting,
            last_renewal_gb,
            pending_renewal_info,
            renewable_plan,
            renewal_plans,
            waiting_renewal,
        )
        from apps.plans.serializers import PlanSerializer

        service = self.get_object()
        plan = renewable_plan(service)
        plans = list(renewal_plans(service))
        if plan is not None and all(p.pk != plan.pk for p in plans):
            plans.insert(0, plan)                    # a retired plan staff marked renewable: listed for this service
        needs_plan = plan is None
        custom = next((p for p in ([plan] if plan else []) + plans if p.type == "custom_volume"), None)
        last_gb = last_renewal_gb(service, custom) if custom else None
        message = ""
        waiting = waiting_renewal(service)
        if waiting is not None:
            # one renewal at a time: the paid one applies first (incident 2026-10-29)
            return Response({
                "can_renew": False, "plan": PlanSerializer(plan).data if plan else None, "plans": [],
                "needs_plan": False, "pending_renewal": pending_renewal_info(service),
                "service": {"id": service.id, "panel_username": service.panel_username},
                "message": RenewalWaiting(waiting).message("fa"),
            })
        if needs_plan:
            message = ("این سرویس پلن تمدید ندارد؛ یک پلن انتخاب کنید. تمدید روی همین اکانت و همین لینک اشتراک انجام می‌شود."
                       if plans else "در حال حاضر پلنی برای تمدید موجود نیست؛ با پشتیبانی تماس بگیرید.")
        return Response({
            "can_renew": bool(plans),
            "plan": PlanSerializer(plan).data if plan else None,
            "plans": PlanSerializer(plans, many=True).data,
            "needs_plan": needs_plan,
            "pending_renewal": None,
            "service": {"id": service.id, "panel_username": service.panel_username},
            "message": message,
            "last_gb": last_gb,
        })

    @action(detail=True, methods=["post"], url_path="renew")
    def renew(self, request, pk=None):
        """Creates a paid-pending renewal order for this service — on the same
        account. Body `plan` (optional) switches / upgrades the plan; without it the
        service's own plan is used (a service without one must send `plan`)."""
        from apps.orders.models import OrderType
        from apps.orders.serializers import OrderSerializer
        from apps.orders.services import OrderError, RenewalWaiting, create_order, renewable_plan, renewal_plans
        from apps.payments_sms.models import BankCard
        from apps.payments_sms.serializers import BankCardSerializer

        service = self.get_object()
        wanted = request.data.get("plan")
        if wanted:
            plan = renewal_plans(service).filter(pk=wanted).first() or (
                renewable_plan(service) if str(getattr(renewable_plan(service), "pk", "")) == str(wanted) else None)
            if plan is None:
                return Response({"detail": "این پلن برای تمدید این سرویس موجود نیست"}, status=400)
        else:
            plan = renewable_plan(service)
            if plan is None:
                return Response({"detail": "یک پلن برای تمدید انتخاب کنید", "code": "needs_plan"}, status=400)

        try:
            gb = request.data.get("custom_volume_gb")
            order = create_order(
                user=request.user, plan_id=plan.id, order_type=OrderType.RENEW,
                service_id=service.id, source="site", custom_volume_gb=int(gb) if str(gb or "").isdigit() else None,
            )
        except RenewalWaiting as exc:
            lang = "en" if getattr(request.user, "language", "fa") == "en" else "fa"
            return Response({"detail": exc.message(lang), "code": exc.code}, status=409)
        except OrderError as exc:
            return Response({"detail": str(exc)}, status=400)

        order_data = OrderSerializer(order).data
        cards = BankCard.objects.filter(is_active=True).order_by("sort_order", "id")
        return Response({
            "order": order_data,
            "payment_instructions": {
                "amount_to_pay": order_data["amount_unique"],
                "reserved_until": order_data["unique_expire_at"],
                "cards": BankCardSerializer(cards, many=True).data,
            },
        }, status=201)

    @action(detail=True, methods=["get"], url_path="qr")
    def qr(self, request, pk=None):
        from .models import customer_sub_url

        service = self.get_object()
        if not customer_sub_url(service):                  # v1.55: «فقط وایرگارد» shows no link / QR
            return HttpResponse(status=404)
        resp = HttpResponse(qr_card_png(service.subscription_url), content_type="image/png")
        resp["Cache-Control"] = "private, max-age=60"
        return resp

    # ------------------------------------------------------------------ v1.55 WireGuard (panel/wireguard.py)
    def _wg(self):
        from . import wireguard as W

        service = self.get_object()                           # the owner's own services only (get_queryset)
        if not service.wireguard:
            raise W.WireguardError("this service has no WireGuard", "این سرویس وایرگارد ندارد", 404)
        return service, W.configs(service)

    def _wg_err(self, exc):
        return Response(exc.payload(), status=exc.status)

    @action(detail=True, methods=["get"], url_path="wireguard", throttle_classes=[WireguardThrottle])
    def wireguard(self, request, pk=None):
        """The service's WireGuard locations (country + flag), one per .conf — generated on demand, never stored."""
        from . import wireguard as W

        try:
            service, confs = self._wg()
        except W.WireguardError as exc:
            return self._wg_err(exc)
        return Response({"results": [W.row(service, c) for c in confs], "all_filename": f"{W.prefix(service)}-{service.id}-wireguard.zip"})

    @action(detail=True, methods=["get"], url_path=r"wireguard/(?P<key>[a-z0-9-]{1,40})", throttle_classes=[WireguardThrottle])
    def wireguard_file(self, request, pk=None, key=None):
        """GET …/wireguard/<location>/ → that location's .conf · …/wireguard/all/ → every location as a zip."""
        from . import wireguard as W

        try:
            service, confs = self._wg()
        except W.WireguardError as exc:
            return self._wg_err(exc)
        if key == "all":
            body, name, ctype = W.zip_all(service, confs), f"{W.prefix(service)}-{service.id}-wireguard.zip", "application/zip"
        else:
            c = next((x for x in confs if x.key == key), None)
            if c is None:
                return Response({"detail": "unknown location", "detail_fa": "این مکان پیدا نشد"}, status=404)
            body, name, ctype = c.body, W.filename(service, c), "application/octet-stream"
        W.audit(service, what=key, via="site", user=request.user)
        resp = HttpResponse(body, content_type=ctype)
        resp["Content-Disposition"] = f'attachment; filename="{name}"'
        resp["Cache-Control"] = "private, no-store"
        resp["X-Content-Type-Options"] = "nosniff"
        return resp

    @action(detail=True, methods=["post"], url_path=r"wireguard/(?P<key>[a-z0-9-]{1,40})/send", throttle_classes=[WireguardThrottle])
    def wireguard_send(self, request, pk=None, key=None):
        """Mini App: the bot sends the .conf (or the zip) to the user's own Telegram chat — WebView downloads are unreliable."""
        from . import wireguard as W
        from apps.telegram.config import sales_client

        user = request.user
        if not getattr(user, "telegram_id", None):
            return Response({"detail": "no Telegram account linked", "detail_fa": "حساب تلگرام به این حساب وصل نیست"}, status=400)
        try:
            service, confs = self._wg()
        except W.WireguardError as exc:
            return self._wg_err(exc)
        client = sales_client()
        if client is None:
            return Response({"detail": "the bot is not available", "detail_fa": "ربات در دسترس نیست"}, status=503)
        if key == "all":
            files = [(f"{W.prefix(service)}-{service.id}-wireguard.zip", W.zip_all(service, confs))]
        else:
            c = next((x for x in confs if x.key == key), None)
            if c is None:
                return Response({"detail": "unknown location", "detail_fa": "این مکان پیدا نشد"}, status=404)
            files = [(W.filename(service, c), c.body)]
        for name, body in files:
            client.send_document_bytes(user.telegram_id, name, body)
        W.audit(service, what=key, via="miniapp", user=user)
        return Response({"ok": True, "message": "Sent to your Telegram chat", "message_fa": "فایل در چت ربات برایتان ارسال شد"})

