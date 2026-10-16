"""Agency panel admin API (/api/v1/admin/agency/…).

GET  agency/                       dashboard (PAMP totals, over-limit list, last sync, switches)
GET  agency/admins/?search=&status=active|panel_disabled|pamp_limited&group=<id>&limit=limited|unlimited
GET  agency/admins/<username>/     every PAMP number + snapshots + recent syncs
POST agency/admins/<username>/<action>/   set-limit {action,value_gb} | remove-limit
                                   | admin-action {action} | reset-deleted-traffic
POST agency/sync-now/
GET  agency/groups/ · POST agency/groups/ {owner,members,note} · DELETE agency/groups/<id>/
GET  agency/sync-logs/?status=
GET/PATCH agency/settings/         {sync_enabled, enforcement_enabled, sync_interval_minutes}

Reads need `agency.view`, writes `agency.manage`. Until the cut-over (sync on)
every write that touches the panel or PAMP's data answers 409 `pre_cutover`.
"""
from __future__ import annotations

from django.db.models import Q
from django.http import Http404
from rest_framework import status
from rest_framework.response import Response

from apps.agency import actions, api
from apps.agency.models import AdminGroup, PanelAdmin, SyncLog
from apps.common.models import write_audit
from apps.settings_app.models import ValueType
from apps.settings_app.utils import get_setting, set_setting

from .base import AdminAPIView

VIEW, MANAGE = ["agency.view"], ["agency.manage"]


def _switches() -> dict:
    return {
        "sync_enabled": bool(get_setting("agency_sync_enabled", False)),
        "enforcement_enabled": bool(get_setting("agency_enforcement_enabled", False)),
        "sync_interval_minutes": int(get_setting("agency_sync_interval_minutes", 15) or 15),
        "writes_enabled": actions.writes_enabled(),
    }


def _run(request, audit_action, target, fn, *args):
    try:
        ok, message = fn(*args)
    except actions.PreCutover as exc:
        return Response({"detail": str(exc), "code": "pre_cutover"}, status=status.HTTP_409_CONFLICT)
    except Exception as exc:  # noqa: BLE001 — panel/API errors are reported, never 500
        return Response({"detail": str(exc)[:200]}, status=status.HTTP_502_BAD_GATEWAY)
    write_audit(action=audit_action, staff=request.user, target=target, detail={"ok": ok, "message": message[:200]})
    return Response({"ok": ok, "message": message}, status=200 if ok else 400)


class AgencyDashboardView(AdminAPIView):
    perms_map = {"GET": VIEW}

    def get(self, request):
        return Response({**api.dashboard(), "switches": _switches()})


class AgencyAdminListView(AdminAPIView):
    perms_map = {"GET": VIEW}

    def get(self, request):
        p = request.query_params
        qs = PanelAdmin.objects.all()
        if p.get("search"):
            qs = qs.filter(username__icontains=p["search"].strip())
        if p.get("limit") == "limited":
            qs = qs.filter(has_data_limit=True, admin_limit_bytes__gt=0)
        elif p.get("limit") == "unlimited":
            qs = qs.filter(Q(has_data_limit=False) | Q(admin_limit_bytes__lte=0))
        groups = list(AdminGroup.objects.all())
        rows = [api.admin_row(a, groups) for a in qs]
        if p.get("status"):
            rows = [r for r in rows if r["status_code"] == p["status"]]
        if p.get("group"):
            rows = [r for r in rows if any(str(g["id"]) == p["group"] for g in r["groups"])]
        return Response({"count": len(rows), "results": rows, "groups": [
            {"id": g.id, "owner": g.owner_username} for g in groups]})


class AgencyAdminDetailView(AdminAPIView):
    perms_map = {"GET": VIEW}

    def get(self, request, username):
        a = PanelAdmin.objects.filter(username=username).first()
        if a is None:
            raise Http404
        return Response({**api.admin_detail(a), "switches": _switches()})


class AgencyAdminActionView(AdminAPIView):
    perms_map = {"POST": MANAGE}
    ACTIONS = {"set-limit", "remove-limit", "admin-action", "reset-deleted-traffic"}

    def post(self, request, username, action):
        if action not in self.ACTIONS:
            raise Http404
        a = PanelAdmin.objects.filter(username=username).first()
        if a is None:
            raise Http404
        d = request.data
        if action == "set-limit":
            return _run(request, "agency.set_limit", a, actions.set_limit, username, d.get("action"), d.get("value_gb"))
        if action == "remove-limit":
            return _run(request, "agency.remove_limit", a, actions.remove_limit, username)
        if action == "admin-action":
            return _run(request, f"agency.{d.get('action')}", a, actions.admin_action, username, d.get("action"))
        return _run(request, "agency.reset_deleted_traffic", a, actions.reset_deleted_traffic, username)


class AgencySyncNowView(AdminAPIView):
    perms_map = {"POST": MANAGE}

    def post(self, request):
        return _run(request, "agency.sync_now", None, actions.sync_now)


class AgencyGroupsView(AdminAPIView):
    perms_map = {"GET": VIEW, "POST": MANAGE, "DELETE": MANAGE}

    def get(self, request):
        names = set(PanelAdmin.objects.values_list("username", flat=True))
        return Response({"results": [
            {"id": g.id, "owner": g.owner_username, "members": g.get_members(), "note": g.note,
             "created_at": g.created_at, "missing": [u for u in g.get_all_usernames() if u not in names]}
            for g in AdminGroup.objects.order_by("owner_username")]})

    def post(self, request):
        d = request.data
        return _run(request, "agency.group_saved", None, actions.save_group, d.get("owner"), d.get("members"),
                    d.get("note"))

    def delete(self, request, group_id=None):
        return _run(request, "agency.group_deleted", None, actions.delete_group, group_id)


class AgencySyncLogsView(AdminAPIView):
    perms_map = {"GET": VIEW}

    def get(self, request):
        qs = SyncLog.objects.order_by("-id")
        if request.query_params.get("status") in ("success", "failed", "partial"):
            qs = qs.filter(status=request.query_params["status"])
        try:
            limit = min(max(int(request.query_params.get("limit", 50)), 1), 200)
            offset = max(int(request.query_params.get("offset", 0)), 0)
        except ValueError:
            limit, offset = 50, 0
        total = qs.count()
        return Response({
            "count": total,
            "summary": {k: SyncLog.objects.filter(status=k).count() for k in ("success", "partial", "failed")},
            "results": [api.sync_row(s) for s in qs[offset:offset + limit]],
            "next": offset + limit if offset + limit < total else None,
        })


class AgencySettingsView(AdminAPIView):
    perms_map = {"GET": VIEW, "PATCH": MANAGE}

    def get(self, request):
        return Response(_switches())

    def patch(self, request):
        d, cur = request.data, _switches()
        sync = bool(d.get("sync_enabled", cur["sync_enabled"]))
        enforce = bool(d.get("enforcement_enabled", cur["enforcement_enabled"]))
        if enforce and not sync:
            return Response({"enforcement_enabled": ["needs sync to be on"]}, status=400)
        if sync and not cur["sync_enabled"] and d.get("confirm") != "FINLAND-STOPPED":
            # turning the sync on IS the cut-over: the Finland PAMP must be stopped first
            return Response({"sync_enabled": ["confirm that the Finland PAMP sync is stopped"]}, status=400)
        try:
            minutes = int(d.get("sync_interval_minutes", cur["sync_interval_minutes"]))
        except (TypeError, ValueError):
            return Response({"sync_interval_minutes": ["a whole number of minutes"]}, status=400)
        if not 1 <= minutes <= 1440:
            return Response({"sync_interval_minutes": ["1–1440 minutes"]}, status=400)
        set_setting("agency_sync_enabled", sync, ValueType.BOOL)
        set_setting("agency_enforcement_enabled", enforce, ValueType.BOOL)
        set_setting("agency_sync_interval_minutes", minutes, ValueType.INT)
        _reschedule(minutes)
        write_audit(action="agency.settings", staff=request.user, target=None,
                    detail={"sync_enabled": sync, "enforcement_enabled": enforce, "interval": minutes})
        return Response(_switches())


def _reschedule(minutes: int) -> None:
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    sched, _ = IntervalSchedule.objects.get_or_create(every=minutes, period=IntervalSchedule.MINUTES)
    for t in PeriodicTask.objects.filter(name="agency: sync panel admins (PAMP)"):
        if t.interval_id != sched.id:
            t.interval = sched
            t.save()          # save() (not update) so django-celery-beat picks the change up
