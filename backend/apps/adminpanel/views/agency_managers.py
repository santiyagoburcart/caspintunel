"""Agency panel → group managers, approvals and group statements (staff side;
rules in apps/agency/managers.py).

GET  agency/managers/                    managers (+ groups, allowed inbounds, cap, pending)
GET  agency/managers/options/            agency groups + PasarGuard roles with their inbounds (live)
POST agency/managers/                    create {username, password, display_name, is_active,
                                         max_unapproved_gb, note, assignments:[{group_id, role_ids}]}
PATCH agency/managers/<id>/              edit / disable (same fields, no password)
POST agency/managers/<id>/password/      {password?} → new password once (generated if empty); sessions end
GET  agency/approvals/?status=pending|approved|rejected|all&group=
GET  agency/approvals/badge/             {pending}
POST agency/approvals/<id>/approve/      {price_per_gb?}   → quota charge (agency.manage + agency.accounting)
POST agency/approvals/<id>/reject/       {reason, confirm: true} → volume taken back on PasarGuard
POST agency/approvals/bulk-approve/      {ids: [...]}
GET  agency/groups/<id>/activity/
GET  agency/ledger/groups/               groups with total debt + pending
GET  agency/ledger/groups/<id>/statement/?from=&to=&export=csv|xlsx
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response

from apps.agency import managers as M
from apps.agency.models import AdminGroup, GroupManager, VolumeRequest
from apps.agency.reports import export_response, parse_day
from apps.common.models import write_audit

from .base import AdminAPIView

VIEW, MANAGE, ACCOUNTING = ["agency.view"], ["agency.manage"], ["agency.accounting"]


class _V(AdminAPIView):
    def handle_exception(self, exc):
        if isinstance(exc, M.ManagerError):
            return Response(exc.payload(), status=exc.status)
        return super().handle_exception(exc)


def _audit_manager(request, action, m, **detail):
    write_audit(action=f"agency.managers.{action}", staff=request.user, target=m,
                detail={"manager": m.username, **detail})


class AgencyManagersView(_V):
    perms_map = {"GET": VIEW, "POST": MANAGE, "PATCH": MANAGE}

    def get(self, request, manager_id=None):
        cat = M._safe_catalog()
        qs = GroupManager.objects.all()
        if manager_id:
            qs = qs.filter(pk=manager_id)
        return Response({"results": [M.manager_row(m, cat) for m in qs], "roles_live": cat is not None})

    def post(self, request, manager_id=None):
        if manager_id:
            return Response(status=405)
        m = M.save_manager(None, request.data or {}, by=request.user.username)
        _audit_manager(request, "created", m, assignments=[(a.group_id, a.allowed_role_ids) for a in m.assignments.all()],
                       max_unapproved_gb=str(m.max_unapproved_gb) if m.max_unapproved_gb is not None else None)
        return Response(M.manager_row(m, M._safe_catalog()), status=status.HTTP_201_CREATED)

    def patch(self, request, manager_id=None):
        data = dict(request.data or {})
        data.pop("username", None)
        data.pop("password", None)
        m = M.save_manager(manager_id, data, by=request.user.username)
        _audit_manager(request, "updated", m, fields=sorted(data),
                       assignments=[(a.group_id, a.allowed_role_ids) for a in m.assignments.all()],
                       is_active=m.is_active,
                       max_unapproved_gb=str(m.max_unapproved_gb) if m.max_unapproved_gb is not None else None)
        return Response(M.manager_row(m, M._safe_catalog()))


class AgencyManagerPasswordView(_V):
    perms_map = {"POST": MANAGE}

    def post(self, request, manager_id):
        m = GroupManager.objects.filter(pk=manager_id).first()
        if m is None:
            return Response({"detail": "manager not found", "code": "not_found"}, status=404)
        pw = M.set_password(m, (request.data or {}).get("password"))
        _audit_manager(request, "password_reset", m)          # never the password
        return Response({"ok": True, "username": m.username, "password": pw})


class AgencyManagerOptionsView(_V):
    perms_map = {"GET": MANAGE}

    def get(self, request):
        return Response(M.options_payload())


class AgencyApprovalsView(_V):
    perms_map = {"GET": VIEW}

    def get(self, request):
        q = request.query_params
        st = q.get("status") or "pending"
        qs = VolumeRequest.objects.select_related("ledger_entry")
        if st != "all":
            qs = qs.filter(status=st)
        if q.get("group"):
            qs = qs.filter(group_id=q["group"])
        if q.get("manager"):
            qs = qs.filter(manager_username=q["manager"])
        try:
            limit = min(max(int(q.get("limit", 200)), 1), 500)
        except ValueError:
            limit = 200
        rows = [M.request_row(r) for r in qs[:limit]]
        pending = [r for r in rows if r["status"] == "pending"]
        return Response({"results": rows, "count": qs.count(), "pending": M.badge(),
                         "pending_gb": sum((r["gb"] for r in pending), 0),
                         "pending_amount": sum((r["amount"] or 0 for r in pending), 0)})


class AgencyApprovalsBadgeView(_V):
    perms_map = {"GET": VIEW}

    def get(self, request):
        return Response({"pending": M.badge()})


class AgencyApprovalActionView(_V):
    perms_map = {"POST": MANAGE}

    def post(self, request, request_id, action):
        d = request.data or {}
        if action == "approve":
            if not request.user.has_perm("agency.accounting"):
                return Response({"detail": "approving records a charge — needs agency.accounting", "code": "forbidden"},
                                status=403)
            r = M.approve(request_id, request.user, price=d.get("price_per_gb"), may_price=True)
            return Response({"ok": True, **M.request_row(r)})
        if action == "reject":
            if d.get("confirm") is not True:
                return Response({"detail": "confirm the reject (it takes the volume back on PasarGuard)",
                                 "code": "confirm"}, status=400)
            r = M.reject(request_id, request.user, d.get("reason", ""))
            return Response({"ok": True, **M.request_row(r)})
        return Response({"detail": "not found"}, status=404)


class AgencyApprovalsBulkView(_V):
    perms_map = {"POST": MANAGE + ACCOUNTING}

    def post(self, request):
        ids = (request.data or {}).get("ids") or []
        if not isinstance(ids, list) or not ids or len(ids) > 200:
            return Response({"detail": "pick 1–200 requests", "code": "invalid"}, status=400)
        done, failed = [], []
        for i in ids:
            try:
                done.append(M.approve(int(i), request.user, may_price=True).id)
            except (M.ManagerError, TypeError, ValueError) as exc:
                failed.append({"id": i, "code": getattr(exc, "code", "invalid"), "detail": str(exc)})
        return Response({"ok": not failed, "approved": done, "failed": failed})


class AgencyGroupActivityView(_V):
    perms_map = {"GET": VIEW}

    def get(self, request, group_id):
        return Response({"results": M.activity([int(group_id)]),
                         "managers": [{"id": a.manager_id, "username": a.manager.username, "is_active": a.manager.is_active}
                                      for a in AdminGroup.objects.get(pk=group_id).manager_assignments.select_related("manager")]
                         if AdminGroup.objects.filter(pk=group_id).exists() else []})


class AgencyGroupLedgerView(_V):
    perms_map = {"GET": ACCOUNTING}

    def get(self, request, group_id=None):
        q = request.query_params
        lang = "en" if q.get("lang") == "en" else "fa"
        if group_id is None:
            out = []
            for g in AdminGroup.objects.order_by("owner_username"):
                st = M.group_statement(g)
                out.append({"id": g.id, "name": M.group_title(g), "owner": g.owner_username,
                            "admins": len(g.get_all_usernames()), "total_debt": st["total_debt"],
                            "pending_gb": st["pending_gb"], "pending_amount": st["pending_amount"],
                            "managers": [a.manager.username for a in g.manager_assignments.select_related("manager")]})
            return Response({"results": out})
        g = AdminGroup.objects.filter(pk=group_id).first()
        if g is None:
            return Response({"detail": "group not found", "code": "not_found"}, status=404)
        frm, to = parse_day(q.get("from")), parse_day(q.get("to"))
        if frm and to and frm > to:
            frm, to = to, frm
        st = M.group_statement(g, frm, to)
        if q.get("export") in ("csv", "xlsx"):
            return export_response(M.group_statement_rows(st, lang), q["export"], f"group-{g.id}-statement", lang)
        return Response(st)
