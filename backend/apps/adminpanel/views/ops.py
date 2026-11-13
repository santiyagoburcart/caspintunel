import logging

from django.db.models import Count, Max, Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.common.models import write_audit
from apps.panel.exceptions import PanelError, PanelLinkNeedsConfirmation, PanelNameTaken, PanelNotFound
from apps.panel.models import Panel, Service, ServiceStatus
from apps.panel.services import (
    ServiceAlreadyLinked,
    client_for,
    create_manual_service,
    delete_service,
    link_existing_service,
    set_service_plan,
    search_panel_users,
    reset_service_usage,
    revoke_subscription,
    set_service_status,
    update_service,
)
from apps.telegram.models import RequiredChannel, TelegramStats

from ..permissions import StaffPermission
from ..serializers import (
    AdminServiceCreateSerializer,
    AdminServiceLinkSerializer,
    AdminServiceRawSerializer,
    AdminServiceSerializer,
    AdminServiceStatusSerializer,
    AdminServiceUpdateSerializer,
)
from .base import AdminAPIView, _AUTH

log = logging.getLogger("caspintunel")
ONLINE_WINDOW_MIN = 5


def _store_quota() -> dict | None:
    from apps.tenancy import quota

    st = quota.state()
    if not st:
        return None
    keep = ("limited", "found", "limit", "available", "percent_remaining")
    out = {k: st.get(k) for k in keep if k in st}
    out["level"] = quota.level_for(st["percent_remaining"]) if st.get("limited") else 0
    return out


def _store_bot() -> dict | None:
    from apps.tenancy import bots, context
    from apps.tenancy.models import Tenant

    return bots.row(Tenant.objects.filter(pk=context.current_tenant_id()).first(), staff_view=False)


def _store_domains() -> list:
    from apps.tenancy import context, domains

    return domains.rows_for(context.current_tenant_id(), staff=False)


class ServiceListViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                         mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """/admin/services/ — the standalone "sold services" admin page: list +
    search/filter, manual creation, and per-row status/reset/revoke/delete/details."""

    authentication_classes = _AUTH
    permission_classes = [StaffPermission]
    # v1.60: on a store's domain the store's own services (tenant-scoped) with the store codes below — opt-in per store,
    # never delete / reset / groups there. The class values are the store's (the release gate reads them); our panel
    # gets OUR_PERMS / OUR_ACTIONS in get_permissions.
    store_ok = True
    perms_map = {"GET": ["services.view"], "POST": ["services.manage"], "PATCH": ["services.manage"],
                 "DELETE": ["services.manage"]}
    action_perms = {"create": ["services.create"], "panel_users": ["services.link"], "link_existing": ["services.link"],
                    "sync_now": ["services.manage"], "sync_one": ["services.manage"]}
    OUR_PERMS = {"GET": ["monitoring.view"], "POST": ["services.manage"], "PATCH": ["services.manage"],
                 "DELETE": ["services.delete"]}
    OUR_ACTIONS = {"panel_users": ["services.manage"], "sync_now": ["services.manage"], "sync_one": ["services.manage"]}
    queryset = Service.objects.none()
    serializer_class = AdminServiceSerializer

    def get_permissions(self):
        from apps.settings_app.branding import is_store

        if not is_store():
            self.perms_map, self.action_perms = self.OUR_PERMS, self.OUR_ACTIONS
        return super().get_permissions()

    @staticmethod
    def _store_refuse(en: str, fa: str, status: int = 403):
        return Response({"detail": en, "detail_fa": fa, "code": "store_refused"}, status=status)

    def get_queryset(self):
        qs = Service.objects.select_related("user", "current_plan", "panel", "scheduled_renewal", "scheduled_renewal__plan").order_by("-created_at")
        kind = self.request.query_params.get("filter")
        if kind == "active":
            qs = qs.filter(status=ServiceStatus.ACTIVE)
        elif kind == "on_hold":
            qs = qs.filter(status=ServiceStatus.ON_HOLD)
        elif kind == "disabled":
            qs = qs.filter(status=ServiceStatus.DISABLED)
        elif kind == "expired":
            qs = qs.filter(status=ServiceStatus.EXPIRED)
        elif kind == "no_plan":
            qs = qs.filter(current_plan__isnull=True)
        elif kind == "online":
            since = timezone.now() - timezone.timedelta(minutes=ONLINE_WINDOW_MIN)
            qs = qs.filter(online_at__gte=since)

        q = (self.request.query_params.get("search") or "").strip()
        if q:
            qs = qs.filter(
                Q(panel_username__icontains=q) | Q(user__username__icontains=q)
                | Q(user__name__icontains=q) | Q(user__telegram_username__icontains=q)
            )
        return qs

    def get_serializer_class(self):
        return AdminServiceCreateSerializer if self.action == "create" else AdminServiceSerializer

    def list(self, request, *args, **kwargs):
        from apps.settings_app.branding import is_store

        resp = super().list(request, *args, **kwargs)
        if is_store():                     # v1.60: never our panel's name on a store's page
            for r in (resp.data.get("results") if isinstance(resp.data, dict) else resp.data) or []:
                r["panel_name"] = None
        resp.data["last_synced_at"] = Service.objects.aggregate(m=Max("last_synced_at"))["m"]
        by_status = dict(Service.objects.values_list("status").annotate(n=Count("id")).values_list("status", "n"))
        resp.data["stats"] = {
            "total": sum(by_status.values()),
            "active": by_status.get(ServiceStatus.ACTIVE, 0),
            "on_hold": by_status.get(ServiceStatus.ON_HOLD, 0),
            "disabled": by_status.get(ServiceStatus.DISABLED, 0),
            "no_plan": Service.objects.filter(current_plan__isnull=True).count(),
        }
        return resp

    def create(self, request, *args, **kwargs):
        """Manual service creation (فاز ۲) — no payment, real panel account."""
        from apps.settings_app.branding import is_store
        from apps.tenancy import quota

        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        store = is_store()
        if store:                          # v1.60: the store's plan on the agency panel, under the reseller (no groups)
            from apps.tenancy import catalog

            if v["plan"].panel_id != catalog.store_panel().id:
                return self._store_refuse("a store service uses the store's own plans only",
                                          "سرویس فروشگاه فقط با پلن‌های خود فروشگاه ساخته می‌شود", 400)
        try:
            service = create_manual_service(
                user=v["user"], plan=v["plan"], panel=None if store else v.get("panel"),
                group_ids=None if store else v.get("group_ids"), account_name=v.get("account_name"),
                staff=request.user,
            )
        except quota.QuotaShort as exc:
            return Response({"detail": str(exc), "detail_fa": "حجم باقی‌ماندهٔ نماینده برای این سرویس کافی نیست — اول حجم را افزایش دهید.",
                             "code": "quota", **{k: exc.detail.get(k) for k in ("need", "available") if k in exc.detail}}, status=409)
        except PanelNameTaken as exc:      # exists on the panel: staff must choose "Link existing account" explicitly
            return Response({"detail": str(exc), "code": "exists_on_panel", "panel_username": exc.username,
                             "owner": exc.owner or ""}, status=409)
        except PanelError as exc:
            return Response({"detail": str(exc)}, status=502)
        return Response(AdminServiceSerializer(service).data, status=201)

    @action(detail=True, methods=["post"], url_path="status")
    def change_status(self, request, pk=None):
        ser = AdminServiceStatusSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            service = set_service_status(int(pk), ser.validated_data["status"], staff=request.user)
        except PanelError as exc:
            return Response({"detail": str(exc)}, status=502)
        return Response(AdminServiceSerializer(service).data)

    @action(detail=True, methods=["post"], url_path="reset")
    def reset_usage(self, request, pk=None):
        from apps.settings_app.branding import is_store

        if is_store():                     # resetting usage would hand out traffic outside the reseller's quota check
            return self._store_refuse("resetting usage is not available in a store", "ریست مصرف در فروشگاه در دسترس نیست")
        try:
            service = reset_service_usage(int(pk), staff=request.user)
        except PanelError as exc:
            return Response({"detail": str(exc)}, status=502)
        return Response(AdminServiceSerializer(service).data)

    @action(detail=True, methods=["post"], url_path="revoke")
    def revoke(self, request, pk=None):
        try:
            service = revoke_subscription(int(pk), staff=request.user)
        except PanelError as exc:
            return Response({"detail": str(exc)}, status=502)
        return Response(AdminServiceSerializer(service).data)

    @extend_schema(request=AdminServiceUpdateSerializer, responses=AdminServiceRawSerializer,
                   summary="Edit a service on the panel (status, volume, expiry, groups, note)")
    def partial_update(self, request, pk=None):
        from datetime import datetime, time
        from zoneinfo import ZoneInfo

        from apps.settings_app.branding import is_store

        service = self.get_object()
        ser = AdminServiceUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        if is_store():                     # v1.60: groups come from the plan; more volume = the reseller's quota
            from apps.tenancy import quota

            if "group_ids" in v:
                return self._store_refuse("groups are set by the store's plan", "گروه‌ها را پلن فروشگاه تعیین می‌کند", 400)
            if "plan" in v and v["plan"] is not None and v["plan"].panel_id != service.panel_id:
                return self._store_refuse("that plan is not on this service's panel", "این پلن برای این سرویس نیست", 400)
            if "data_limit_gb" in v:
                new = int(v["data_limit_gb"] * 1024 ** 3)
                if new == 0 or (service.data_limit and new > service.data_limit) or not service.data_limit:
                    need = None if new == 0 else new - int(service.data_limit or 0)
                    try:
                        quota.check(need, what="service edit")
                    except quota.QuotaShort as exc:
                        return Response({"detail": str(exc), "code": "quota",
                                         "detail_fa": "حجم باقی‌ماندهٔ نماینده برای این افزایش کافی نیست."}, status=409)
        kw = {}
        if "status" in v:
            kw["status"] = v["status"]
        if "data_limit_gb" in v:
            kw["data_limit"] = int(v["data_limit_gb"] * 1024 ** 3)
        if "expire_date" in v:
            d = v["expire_date"]
            kw["expire_at"] = (datetime.combine(d, time(23, 59, 59), tzinfo=ZoneInfo("Asia/Tehran"))
                               if d else None)
        for key in ("on_hold_days", "group_ids", "note"):
            if key in v:
                kw[key] = v[key]
        if "hwid_limit" in v:
            kw["hwid_limit"] = v["hwid_limit"] or 0
        if "plan" in v:
            try:
                service = set_service_plan(service.id, v["plan"], staff=request.user)
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=400)
            if not kw:                         # only the plan changed: nothing to send to PasarGuard
                raw = None
                try:
                    raw = client_for(service.panel).get_user(service.panel_username)
                except PanelError as exc:
                    log.info("plan change: live read of service %s failed: %s", service.id, exc)
                return Response(AdminServiceRawSerializer(service, context={"panel_raw": raw}).data)
        try:
            service, raw = update_service(service.id, staff=request.user, **kw)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        except PanelError as exc:
            return Response({"detail": str(exc)}, status=502)
        return Response(AdminServiceRawSerializer(service, context={"panel_raw": raw}).data)

    def destroy(self, request, *args, **kwargs):
        from apps.settings_app.branding import is_store

        if is_store():                     # a store disables a service, never deletes the PasarGuard account
            return self._store_refuse("deleting a service is not available in a store", "حذف سرویس در فروشگاه در دسترس نیست")
        instance = self.get_object()
        try:
            delete_service(instance.id, staff=request.user)
        except PanelError as exc:
            return Response({"detail": str(exc)}, status=502)
        return Response(status=204)

    @action(detail=True, methods=["get"], url_path="panel-detail")
    def panel_detail(self, request, pk=None):
        """Everything PasarGuard returns for this account, live — the
        "جزئیات" modal (raw + our formatted fields in one response)."""
        service = self.get_object()
        raw = None
        try:
            raw = client_for(service.panel).get_user(service.panel_username)
        except PanelError as exc:
            log.info("panel-detail live fetch failed for service %s: %s", service.id, exc)
        data = AdminServiceRawSerializer(service, context={"panel_raw": raw}).data
        return Response(data)

    @action(detail=False, methods=["get"], url_path="panel-users")
    def panel_users(self, request):
        """Live search of a panel's accounts (?panel=<id>&search=<username>) for
        "link an existing panel account" — each row says if it's already linked."""
        from apps.settings_app.branding import is_store

        owner = None
        if is_store():                     # v1.60: only the reseller's own PasarGuard users, on the agency panel
            from apps.tenancy import catalog

            panel, owner = catalog.store_panel(), (catalog.current_store().reseller_username or "-")
        else:
            panel = Panel.objects.filter(pk=request.query_params.get("panel") or 0, is_active=True).first()
        if panel is None:
            return Response({"detail": "unknown or inactive panel"}, status=400)
        try:
            rows = search_panel_users(panel, request.query_params.get("search") or "", limit=20, owner=owner)
            if owner is not None:          # mark rows linked in another store / ours (never whose)
                from apps.tenancy.context import current_tenant_id
                from apps.tenancy.importers.engine import linked_anywhere

                where = linked_anywhere(panel, {r["username"].lower() for r in rows if r["username"]})
                for r in rows:
                    tid = where.get((r["username"] or "").lower())
                    r["linked_elsewhere"] = bool(tid and tid != current_tenant_id())
                    r["other_admin"] = False
        except PanelError as exc:
            if owner is not None:          # a store: PasarGuard unreachable is shown in the dialog, never a 5xx page
                return Response({"results": [], "unavailable": True, "detail": "the panel is not reachable right now",
                                 "detail_fa": "پنل پاسارگارد الان در دسترس نیست — کمی بعد دوباره جستجو کنید."})
            return Response({"detail": str(exc)}, status=502)
        return Response({"results": rows})

    @action(detail=False, methods=["post"], url_path="link")
    def link_existing(self, request):
        """Adopt an existing panel account: our Service (synced from the panel) +
        an `imported` Order with no payment. Nothing changes on the panel."""
        from apps.settings_app.branding import is_store

        data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        owner = None
        if is_store():                     # v1.60: the agency panel, and ONLY an account the reseller's admin owns
            from apps.tenancy import catalog

            data["panel"] = catalog.store_panel().id
            data["confirm_other_admin"] = False
            owner = catalog.current_store().reseller_username or "-"
        ser = AdminServiceLinkSerializer(data=data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        if owner is not None:              # linked in another store (or ours)? say so without showing whose
            from apps.tenancy.context import current_tenant_id
            from apps.tenancy.importers.engine import linked_anywhere

            where = linked_anywhere(v["panel"], {v["panel_username"].strip().lower()})
            if where and set(where.values()) != {current_tenant_id()}:
                return Response({"detail": "already linked to a customer elsewhere", "code": "linked_elsewhere",
                                 "detail_fa": "این کاربر قبلاً به مشتری دیگری وصل شده است."}, status=409)
        try:
            service = link_existing_service(user=v["user"], panel=v["panel"], panel_username=v["panel_username"],
                                            plan=v.get("plan"), staff=request.user,
                                            confirm_other_admin=v.get("confirm_other_admin", False), owner_must_be=owner)
        except PanelLinkNeedsConfirmation as exc:
            if owner is not None:
                return Response({"detail": f"{exc.username} belongs to another admin", "code": "not_reseller",
                                 "detail_fa": "این کاربر متعلق به ادمین دیگری است — فقط کاربران خود نماینده قابل اتصال‌اند."}, status=403)
            return Response({"detail": str(exc), "code": "other_admin", "panel_username": exc.username,
                             "owner": exc.owner}, status=409)
        except ServiceAlreadyLinked as exc:
            return Response({"detail": str(exc), "service_id": exc.service.id,
                             "user_id": exc.service.user_id, "username": exc.service.user.username}, status=409)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        except PanelNotFound:
            return Response({"detail": "no such account on the panel"}, status=404)
        except PanelError as exc:
            return Response({"detail": str(exc)}, status=502)
        return Response(AdminServiceSerializer(service).data, status=201)

    @action(detail=False, methods=["post"], url_path="sync-now")
    def sync_now(self, request):
        """Run the sync now and say what it did: {checked, updated, errors, skipped, rows}.
        Whatever does not fit in the request time goes on in the background (`skipped`)."""
        from apps.panel.services import sync_services, syncable_services
        from apps.panel.tasks import sync_services_task

        ids = list(syncable_services().order_by("id").values_list("id", flat=True))
        res = sync_services(ids, budget_seconds=40)
        rest = res.pop("skipped_ids", None)
        if rest:
            sync_services_task.delay(rest)
        res["rows"] = res["rows"][:50]
        res["last_synced_at"] = Service.objects.aggregate(m=Max("last_synced_at"))["m"]
        write_audit(action="service.sync_all", staff=request.user,
                    detail={k: res[k] for k in ("checked", "updated", "errors", "skipped")})
        return Response(res)

    @action(detail=True, methods=["post"], url_path="sync")
    def sync_one(self, request, pk=None):
        """Sync this one service from its panel now: {checked, updated, errors, rows, service}."""
        from apps.panel.services import sync_services

        service = self.get_object()
        res = sync_services([service.id])
        res.pop("skipped_ids", None)
        service.refresh_from_db()
        res["service"] = AdminServiceSerializer(service).data
        return Response(res)


def _store_active_topics() -> int:
    from apps.tickets.models import TicketTopic

    return TicketTopic.objects.filter(is_active=True).count()


def _store_failed_orders() -> int:
    from apps.tenancy import failed_orders

    return failed_orders.count()


def _store_fee_due():
    from apps.tenancy import context, fees

    return fees.store_banner(context.store_id())


class DashboardView(AdminAPIView):
    perms_map = {"GET": ["monitoring.view"]}
    store_ok = True                      # v1.43: a store sees its own services; server health stays ours

    @extend_schema(summary="Panel overview counters", responses=dict)
    def get(self, request):
        from django.db.models import Max

        from apps.ops.models import HealthCheck, ResourceStat

        by_status = dict(
            Service.objects.values_list("status").annotate(n=Count("id")).values_list("status", "n")
        )
        since = timezone.now() - timezone.timedelta(minutes=ONLINE_WINDOW_MIN)

        latest_ids = HealthCheck.objects.values("target").annotate(last=Max("id")).values_list("last", flat=True)
        checks = list(HealthCheck.objects.filter(id__in=list(latest_ids)))
        res = ResourceStat.objects.order_by("-sampled_at").first()

        from apps.settings_app.branding import is_store

        if is_store():
            return Response({"services": {"total": sum(by_status.values()), "by_status": by_status,
                                          "online_now": Service.objects.filter(online_at__gte=since).count()},
                             "health": None, "resources": None, "store": True,
                             # v1.45: the store's own domains, read-only (state, certificate, health — no records / errors)
                             "domains": _store_domains(),
                             # v1.46: the reseller's quota left for this store (banner at 20 % / 10 %)
                             "quota": _store_quota(),
                             # v1.49: the store's own bot, read-only (username + state; the token never leaves the server)
                             "bot": _store_bot(),
                             # v1.52.1: warnings — no active ticket topic (customers can't open tickets) · «ساخت ناموفق» orders
                             "ticket_topics_active": _store_active_topics(),
                             "failed_orders": _store_failed_orders(),
                             # v1.53: the store's unpaid monthly fee (tenancy/fees.py; None while nothing is open)
                             "fee_due": _store_fee_due()})
        return Response({
            "services": {
                "total": sum(by_status.values()),
                "by_status": by_status,
                "online_now": Service.objects.filter(online_at__gte=since).count(),
            },
            "health": {
                "up": sum(1 for c in checks if c.is_up),
                "down": [c.target for c in checks if not c.is_up],
            },
            "resources": {
                "cpu_percent": res.cpu_percent if res else None,
                "ram_percent": res.ram_percent if res else None,
                "disk_percent": res.disk_percent if res else None,
                "sampled_at": res.sampled_at if res else None,
            },
        })


class TelegramStatsView(AdminAPIView):
    perms_map = {"GET": ["monitoring.view"]}

    @extend_schema(summary="Forced-channel member counts + latest bot stats", responses=dict)
    def get(self, request):
        channels = list(
            RequiredChannel.objects.filter(is_active=True)
            .values("channel_id", "title", "member_count", "last_synced_at")
        )
        latest = TelegramStats.objects.order_by("-sampled_at").first()
        return Response({
            "channels": channels,
            "channel_total": sum(c["member_count"] for c in channels),
            "bot_member_count": latest.bot_member_count if latest else None,
            "overlap_bot_channels": latest.overlap_bot_channels if latest else None,
            "sampled_at": latest.sampled_at if latest else None,
        })
