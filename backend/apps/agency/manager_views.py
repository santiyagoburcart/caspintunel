"""/api/v1/agency/manager/ — the group-manager portal API (manager sessions only;
apps/agency/managers.py has the rules). Everything is scoped to the manager's own
groups; anything else answers 403.

POST login/ {username, password} → {token, expires_at}      (throttle "auth", per-username lockout)
POST logout/
GET  me/                             manager, groups (admins + allowed inbounds), cap, pending
POST admins/ {group_id, username, password, role_id, initial_gb}       create (live at once, pending approval)
POST admins/<u>/add-volume/ {gb}     increase only (live at once, pending approval)
POST admins/<u>/password/ {password}
POST admins/<u>/inbounds/ {role_id}  allowed list only
GET  admins/<u>/statement/?from=&to=&export=csv|xlsx
GET  accounting/?group=&from=&to=&export=csv|xlsx
GET  groups/<id>/statement/?from=&to=&export=csv|xlsx
GET  activity/?group=
anything else under manager/ (set-limit, remove-limit, delete, prices, payments, roles…) → 403
"""
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import managers as M
from .models import PanelAdmin
from .reports import export_response, parse_day


def _ip(request):
    return request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("REMOTE_ADDR", "")


def _err(exc: M.ManagerError) -> Response:
    return Response(exc.payload(), status=exc.status)


class _Mgr(APIView):
    authentication_classes = [M.ManagerTokenAuthentication]
    permission_classes = [M.IsManager]

    @property
    def m(self):
        return self.request.user.manager

    def handle_exception(self, exc):
        if isinstance(exc, M.ManagerError):
            return _err(exc)
        return super().handle_exception(exc)

    def range(self):
        q = self.request.query_params
        frm, to = parse_day(q.get("from")), parse_day(q.get("to"))
        if frm and to and frm > to:
            frm, to = to, frm
        return frm, to

    def lang(self):
        return "en" if self.request.query_params.get("lang") == "en" else "fa"


class ManagerLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        token = M.login(request.data.get("username", ""), request.data.get("password", ""), _ip(request))
        if not token:
            return Response({"detail": "Wrong username or password."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"token": token, "expires_at": timezone.now() + M.SESSION_AGE})


class ManagerLogoutView(_Mgr):
    def post(self, request):
        request.auth.revoked = True
        request.auth.save(update_fields=["revoked"])
        return Response(status=status.HTTP_204_NO_CONTENT)


def _admin_row(a: PanelAdmin, cat) -> dict:
    from . import api

    row = api.admin_row(a)
    row.pop("groups", None)
    role = (a.raw_data or {}).get("role") or {}
    row["role"] = M._role_view(role["id"], cat) if role.get("id") else None
    row["admin_limit_bytes"] = a.admin_limit_bytes if a.has_data_limit else 0
    row["is_sudo"] = a.is_sudo
    return row


class ManagerMeView(_Mgr):
    def get(self, request):
        from . import ledger

        m = self.m
        cat = M._safe_catalog()
        bal = ledger.balances()
        pend = {}
        for p in M._pending_rows(M.visible_usernames(m)):
            x = pend.setdefault(p["admin"], {"gb": 0, "count": 0})
            x["gb"] += p["gb"]; x["count"] += 1
        groups = []
        for asg in M.assignments(m):
            g = asg.group
            admins = {a.username: a for a in PanelAdmin.objects.filter(username__in=g.get_all_usernames())}
            rows = []
            for u in g.get_all_usernames():
                if u in admins:
                    r = _admin_row(admins[u], cat)
                    r.update({"balance": bal.get(u, 0), "pending": pend.get(u, {"gb": 0, "count": 0}),
                              "member_role": "owner" if u == g.owner_username else "member"})
                    rows.append(r)
            groups.append({"id": g.id, "name": M.group_title(g), "owner": g.owner_username, "admins": rows,
                           "roles": [M._role_view(r, cat) for r in asg.allowed_role_ids
                                     if not M._role_view(r, cat)["is_owner"]],
                           "total_debt": sum((bal.get(u, 0) for u in g.get_all_usernames()), 0)})
        return Response({"manager": {"username": m.username, "display_name": m.display_name},
                         "groups": groups, "cap": M.cap_state(m), "roles_live": cat is not None,
                         "writes_enabled": _writes()})


def _writes() -> bool:
    from .actions import writes_enabled

    return writes_enabled()


class ManagerAdminCreateView(_Mgr):
    def post(self, request):
        out = M.create_admin(self.m, request.data or {})
        return Response({**out, "ok": True}, status=201)


class ManagerAdminActionView(_Mgr):
    ACTIONS = {"add-volume", "password", "inbounds"}

    def post(self, request, username, action):
        d = request.data or {}
        if action == "add-volume":
            return Response({**M.add_volume(self.m, username, d.get("gb")), "ok": True})
        if action == "password":
            return Response(M.change_password(self.m, username, d.get("password")))
        if action == "inbounds":
            return Response(M.change_inbounds(self.m, username, d.get("role_id")))
        raise M.forbidden()


class ManagerAdminStatementView(_Mgr):
    def get(self, request, username):
        M.assignment_for_admin(self.m, username)
        frm, to = self.range()
        st = M.admin_statement(username, frm, to)
        fmt = request.query_params.get("export")
        if fmt in ("csv", "xlsx"):
            return export_response(M.statement_rows(st, self.lang()), fmt, f"statement-{_safe(username)}", self.lang())
        return Response(st)


class ManagerAccountingView(_Mgr):
    def get(self, request):
        m = self.m
        gid = request.query_params.get("group")
        asgs = [M.assignment_for_group(m, gid)] if gid else M.assignments(m)
        frm, to = self.range()
        out = []
        for a in asgs:
            rows = M.admin_summaries(a.group.get_all_usernames(), frm, to)
            out.append({"id": a.group_id, "name": M.group_title(a.group), "admins": rows,
                        "total_debt": sum((r["balance"] for r in rows), 0),
                        "pending_gb": sum((r["pending"]["gb"] for r in rows), 0),
                        "pending_amount": sum((r["pending"]["amount"] for r in rows), 0)})
        fmt = request.query_params.get("export")
        if fmt in ("csv", "xlsx"):
            rows = []
            for g in out:
                rows += g["admins"]
            return export_response(M.summary_rows(rows, self.lang()), fmt, "accounting", self.lang())
        return Response({"groups": out, "from": frm, "to": to})


class ManagerGroupStatementView(_Mgr):
    def get(self, request, group_id):
        a = M.assignment_for_group(self.m, group_id)
        frm, to = self.range()
        st = M.group_statement(a.group, frm, to)
        fmt = request.query_params.get("export")
        if fmt in ("csv", "xlsx"):
            return export_response(M.group_statement_rows(st, self.lang()), fmt, f"group-{a.group_id}-statement", self.lang())
        return Response(st)


class ManagerActivityView(_Mgr):
    def get(self, request):
        gid = request.query_params.get("group")
        ids = [M.assignment_for_group(self.m, gid).group_id] if gid else [a.group_id for a in M.assignments(self.m)]
        return Response({"results": M.activity(ids)})


class ManagerForbiddenView(_Mgr):
    """Everything else a manager might try (set-limit, remove-limit, reduce, unlimited, delete
    admins, roles, prices, payments, other endpoints) — an explicit 403, never a 404."""

    def _no(self, request, *args, **kwargs):
        raise M.forbidden()

    get = post = put = patch = delete = _no


def _safe(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "-_") or "admin"
