"""/api/v1/agency/manager/ — the group-manager API (apps/agency/managers.py has the rules).
Since v1.25 a manager signs in to /panel/ as a staff account (role "Group manager") and
calls this API with its normal staff JWT; only a staff linked to an active GroupManager
passes (IsGroupManagerStaff). Everything is scoped to the manager's own groups; anything
else answers 403. Every other /api/v1/admin/ endpoint refuses such a staff (StaffPermission).

GET  me/                             manager, groups (admins + allowed admin roles, names only), cap, pending
POST admins/ {group_id, username, password, role_id, initial_gb}       create (live at once, pending approval)
POST admins/<u>/add-volume/ {gb}     increase only (live at once, pending approval)
POST admins/<u>/password/ {password}
POST admins/<u>/role/ {role_id}      allowed admin roles only
GET  admins/<u>/statement/?from=&to=&export=csv|xlsx
GET  accounting/?group=&from=&to=&export=csv|xlsx
GET  groups/<id>/statement/?from=&to=&export=csv|xlsx
GET  activity/?group=
POST login/ · logout/                410 — sign in at /panel/ (the old portal login is gone)
anything else under manager/ (set-limit, remove-limit, delete, prices, payments, roles…) → 403
"""
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.adminpanel.permissions import IsGroupManagerStaff, StaffJWTAuthentication

from . import managers as M
from .models import PanelAdmin
from .reports import export_response, parse_day


def _err(exc: M.ManagerError) -> Response:
    return Response(exc.payload(), status=exc.status)


class _Mgr(APIView):
    authentication_classes = [StaffJWTAuthentication]
    permission_classes = [IsGroupManagerStaff]

    @property
    def m(self):
        return self.request.user.group_manager_row

    def need(self, code: str):
        """v1.27: each ability is its own permission of the manager's role (Roles page)."""
        if not self.request.user.has_perm(code):
            raise M.ManagerError("your role does not allow this", "forbidden", None, permission=code)

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


class ManagerPasswordView(_Mgr):
    """A manager changes its OWN panel password (v1.25.5, Settings tab). Needs the current
    password; ends every other session (token_version) and hands back fresh tokens for
    this one. The GroupManager keeps the same hash."""
    throttle_scope = "auth"

    def post(self, request):
        from django.db import transaction

        from apps.adminpanel.tokens import issue_tokens
        from apps.common.models import write_audit

        cur = str(request.data.get("current_password") or "")
        new = str(request.data.get("new_password") or "")
        staff = request.user
        if not staff.check_password(cur):
            return Response({"detail": "the current password is wrong", "code": "wrong_password",
                             "field": "current_password"}, status=400)
        if len(new) < 8:
            return Response({"detail": "password: at least 8 characters", "code": "invalid",
                             "field": "new_password"}, status=400)
        if new == cur:
            return Response({"detail": "the new password is the same as the current one", "code": "same",
                             "field": "new_password"}, status=400)
        with transaction.atomic():
            staff.set_password(new)                      # bumps token_version → other sessions end
            staff.save(update_fields=["password_hash", "token_version", "updated_at"])
            M.GroupManager.objects.filter(pk=self.m.pk).update(password=staff.password_hash)
            write_audit(action="agency.manager.own_password_changed", staff=staff, target=self.m,
                        detail={"manager": self.m.username}, ip=request.META.get("REMOTE_ADDR"))
        return Response({"detail": "password changed", **issue_tokens(staff)})


class ManagerLoginGoneView(APIView):
    """The separate manager portal login is gone (v1.25): managers sign in at /panel/."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        return Response({"detail": "Group managers now sign in to the main panel (/panel/) with the same "
                                   "username and password.", "code": "moved", "login": "/panel/login"}, status=410)

    get = post


FULL_KEYS = ("total_sold_fmt", "sold_limit_fmt", "sold_limit_value", "hidden_fmt", "user_counts")
FULL_BYTES = ("total_sold", "sold_limit", "hidden", "hidden_clamped", "deleted")


def _admin_row(a: PanelAdmin, cat, full: bool = False) -> dict:
    """v1.36: `full` (agency.gm.full_stats) = the staff Agency page numbers, same PAMP formulas
    (api.admin_row / admin_detail); without it those keys never leave the server."""
    from . import api
    from .enrich import _enrich

    row = api.admin_row(a)
    row.pop("groups", None)
    role = (a.raw_data or {}).get("role") or {}
    row["role"] = M.mgr_role(role.get("id"), cat)            # v1.27.1: name only
    row["admin_limit_bytes"] = a.admin_limit_bytes if a.has_data_limit else 0
    row["is_sudo"] = a.is_sudo
    if full:
        e = _enrich(a)
        row.update({"deleted_used_fmt": e["deleted_used_fmt"], "hidden_clamped_fmt": a.hidden_traffic_fmt,
                    "deleted_traffic_reset_at": a.deleted_traffic_reset_at})
    else:
        for k in FULL_KEYS:
            row.pop(k, None)
        for k in FULL_BYTES:
            (row.get("bytes") or {}).pop(k, None)
    return row


LIVE_TTL = 60


def live_stats(usernames: list[str]) -> dict:
    """v1.36 per admin, live from PasarGuard (read-only, cached 60 s): user counts by status, online now,
    last time one of its users was online. One failing admin never breaks the others."""
    from concurrent.futures import ThreadPoolExecutor

    from django.core.cache import cache

    from apps.panel.client import PasarGuardClient

    from .panel_api import agency_panel

    out, todo = {}, []
    for u in usernames:
        hit = cache.get(f"agency:gm:live:{u}")
        if hit is not None:
            out[u] = hit
        else:
            todo.append(u)
    if not todo:
        return out
    c = PasarGuardClient(agency_panel())
    c._token()                                   # one login in this thread; the workers reuse it

    def one(u):
        try:
            s = c._request("GET", "/api/system/users", params={"admin_username": u})
            last = c._request("GET", "/api/users", params={"admin": u, "sort": "-online_at", "limit": 1})
            users = (last or {}).get("users") or []
            row = {"total": s.get("total_user", 0), "online": s.get("online_users", 0), "active": s.get("active_users", 0),
                   "on_hold": s.get("on_hold_users", 0), "disabled": s.get("disabled_users", 0),
                   "expired": s.get("expired_users", 0), "limited": s.get("limited_users", 0),
                   "last_online": users[0].get("online_at") if users else None, "ok": True}
        except Exception:  # noqa: BLE001 — shown as "—" for this admin
            return u, {"ok": False}
        cache.set(f"agency:gm:live:{u}", row, LIVE_TTL)
        return u, row

    with ThreadPoolExecutor(max_workers=8) as ex:
        for u, row in ex.map(one, todo):
            out[u] = row
    return out


class ManagerAdminsLiveView(_Mgr):
    """v1.36 GET manager/admins/live/?u=a&u=b — live user counts, online, last activity (own groups only)."""

    def get(self, request):
        self.need("agency.gm.full_stats")
        mine = set(M.visible_usernames(self.m))
        names = [u for u in request.query_params.getlist("u") if u in mine][:60]
        return Response({"results": live_stats(names)})


class ManagerAdminStatsView(_Mgr):
    """v1.36 GET manager/admins/<username>/stats/ — the full numbers of one admin + live counts."""

    def get(self, request, username):
        self.need("agency.gm.full_stats")
        if username not in M.visible_usernames(self.m):
            return Response({"detail": "not an admin of your groups", "detail_fa": "این ادمین در گروه‌های شما نیست"}, status=403)
        a = PanelAdmin.objects.filter(username=username).first()
        if a is None:
            return Response({"detail": "not found"}, status=404)
        row = _admin_row(a, M._safe_catalog(), full=True)
        row["live"] = live_stats([username]).get(username, {"ok": False})
        return Response(row)


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
        # v1.37: ?lite=1 → groups without their admin rows (the admins page pages them: GET manager/admins/)
        see_admins = self.request.user.has_perm("agency.gm.view_admins") and not request.query_params.get("lite")
        for asg in M.assignments(m):
            g = asg.group
            admins = {a.username: a for a in PanelAdmin.objects.filter(username__in=g.get_all_usernames())}
            rows = []
            for u in (g.get_all_usernames() if see_admins else []):
                if u in admins:
                    r = _admin_row(admins[u], cat, full=self.request.user.has_perm("agency.gm.full_stats"))
                    r.update({"balance": bal.get(u, 0), "pending": pend.get(u, {"gb": 0, "count": 0}),
                              "member_role": "owner" if u == g.owner_username else "member"})
                    rows.append(r)
            groups.append({"id": g.id, "name": M.group_title(g), "owner": g.owner_username, "admins": rows,
                           "roles": M.allowed_roles(asg, cat),
                           "total_debt": sum((bal.get(u, 0) for u in g.get_all_usernames()), 0)
                           if self.request.user.has_perm("agency.gm.accounting") else None})
        staff = self.request.user
        return Response({"manager": {"username": m.username, "display_name": m.display_name,
                                     "role": staff.role.name if staff.role_id else "",
                                     "role_fa": (staff.role.name_fa or "") if staff.role_id else "",
                                     "max_unapproved_gb": m.max_unapproved_gb},
                         "groups": groups, "cap": M.cap_state(m), "roles_live": cat is not None,
                         "permissions": self.request.user.gm_permissions(),
                         "writes_enabled": _writes()})


def _writes() -> bool:
    from .actions import writes_enabled

    return writes_enabled()


PAGE_SIZES = (10, 20, 50, 100)


class ManagerAdminCreateView(_Mgr):
    def get(self, request):
        """v1.37 «ادمین‌های گروه»: own groups' admins, searched over ALL of them, sorted, 20 per page.
        ?q= &sort=name|usage|debt &group= &page= &page_size="""
        from . import ledger

        self.need("agency.gm.view_admins")
        q = request.query_params
        full = request.user.has_perm("agency.gm.full_stats")
        see_debt = request.user.has_perm("agency.gm.accounting")
        cat = M._safe_catalog()
        bal = ledger.balances()
        pend = {}
        for p in M._pending_rows(M.visible_usernames(self.m)):
            x = pend.setdefault(p["admin"], {"gb": 0, "count": 0})
            x["gb"] += p["gb"]; x["count"] += 1
        term = (q.get("q") or "").strip().lower()
        rows, seen = [], set()
        for asg in M.assignments(self.m):
            g = asg.group
            if q.get("group") and str(g.id) != str(q.get("group")):
                continue
            names = [u for u in g.get_all_usernames() if u not in seen and (not term or term in u.lower())]
            admins = {a.username: a for a in PanelAdmin.objects.filter(username__in=names)}
            for u in names:
                if u not in admins:
                    continue
                seen.add(u)
                r = _admin_row(admins[u], cat, full=full)
                r.update({"balance": bal.get(u, 0) if see_debt else None, "pending": pend.get(u, {"gb": 0, "count": 0}),
                          "member_role": "owner" if u == g.owner_username else "member",
                          "group_id": g.id, "group": M.group_title(g)})
                rows.append(r)
        sort = q.get("sort") or "name"
        if sort == "usage":
            rows.sort(key=lambda r: (r["is_unlimited"], -(r["usage_percent"] or 0), r["username"].lower()))
        elif sort == "debt" and see_debt:
            rows.sort(key=lambda r: (-(r["balance"] or 0), r["username"].lower()))
        else:
            sort = "name"
            rows.sort(key=lambda r: (r["member_role"] != "owner", r["username"].lower()))
        try:
            size = int(q.get("page_size") or 20)
        except ValueError:
            size = 20
        size = size if size in PAGE_SIZES else 20
        count = len(rows)
        pages = max(1, -(-count // size))
        try:
            page = min(max(1, int(q.get("page") or 1)), pages)
        except ValueError:
            page = 1
        return Response({"results": rows[(page - 1) * size: page * size], "count": count, "page": page, "pages": pages,
                         "page_size": size, "sort": sort})

    def post(self, request):
        self.need("agency.gm.create_admin")
        out = M.create_admin(self.m, request.data or {})
        return Response({**out, "ok": True}, status=201)


class ManagerAdminActionView(_Mgr):
    ACTIONS = {"add-volume", "password", "role", "enable", "disable", "profile", "users"}

    def get(self, request, username, action):
        q = request.query_params
        if action == "profile":
            self.need("agency.gm.create_admin")
            return Response(M.admin_profile(self.m, username))
        if action == "users":
            self.need("agency.gm.view_users")
            return Response(M.admin_users(self.m, username, search=q.get("search") or "", status=q.get("status") or "",
                                          offset=q.get("offset") or 0, limit=q.get("limit") or 20))
        raise M.forbidden()

    def post(self, request, username, action):
        d = request.data or {}
        if action in ("enable", "disable"):
            self.need("agency.gm.toggle_admin")
            return Response(M.set_admin_status(self.m, username, action == "enable"))
        if action == "profile":
            self.need("agency.gm.create_admin")
            return Response(M.update_admin_profile(self.m, username, d))
        if action == "add-volume":
            self.need("agency.gm.add_volume")
            return Response({**M.add_volume(self.m, username, d.get("gb")), "ok": True})
        if action == "password":
            self.need("agency.gm.admin_password")
            return Response(M.change_password(self.m, username, d.get("password")))
        if action == "role":
            self.need("agency.gm.admin_role")
            return Response(M.change_role(self.m, username, d.get("role_id")))
        raise M.forbidden()


class ManagerAdminStatementView(_Mgr):
    def get(self, request, username):
        self.need("agency.gm.accounting")
        M.assignment_for_admin(self.m, username)
        frm, to = self.range()
        st = M.admin_statement(username, frm, to)
        fmt = request.query_params.get("export")
        if fmt in ("csv", "xlsx"):
            return export_response(M.statement_rows(st, self.lang()), fmt, f"statement-{_safe(username)}", self.lang())
        return Response(st)


class ManagerAccountingView(_Mgr):
    def get(self, request):
        self.need("agency.gm.accounting")
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
        self.need("agency.gm.accounting")
        a = M.assignment_for_group(self.m, group_id)
        frm, to = self.range()
        st = M.group_statement(a.group, frm, to)
        fmt = request.query_params.get("export")
        if fmt in ("csv", "xlsx"):
            return export_response(M.group_statement_rows(st, self.lang()), fmt, f"group-{a.group_id}-statement", self.lang())
        return Response(st)


class ManagerActivityView(_Mgr):
    def get(self, request):
        self.need("agency.gm.activity")
        gid = request.query_params.get("group")
        ids = [M.assignment_for_group(self.m, gid).group_id] if gid else [a.group_id for a in M.assignments(self.m)]
        # v1.37: type / admin filters + pages; the manager API never talks about inbounds (old rows carried them)
        q = request.query_params
        admin = q.get("admin") or ""
        if admin and admin not in M.visible_usernames(self.m):
            admin = "__none__"
        return Response(M.manager_activity(self.m, ids, kind=q.get("type") or "", admin=admin,
                                           page=q.get("page") or 1, size=q.get("page_size") or 30))


class ManagerPrefsView(_Mgr):
    """v1.37 the manager's own sound preference (same storage as staff: Staff.notify_prefs)."""

    def get(self, request):
        from apps.adminpanel.views.push import staff_prefs

        return Response(staff_prefs(request.user))

    def patch(self, request):
        from apps.adminpanel.views.push import StaffPrefsView

        return StaffPrefsView.patch(self, request)

    put = patch


class ManagerPushView(_Mgr):
    """v1.37 Web Push for the manager's own browsers (notices arrive while the panel is closed)."""

    def get(self, request):
        from apps.notifications import webpush

        return Response({"enabled": webpush.enabled(), "public_key": webpush.public_key(),
                         "subscriptions": request.user.push_subscriptions.count()})

    def post(self, request, action=None):
        from apps.adminpanel.views.push import StaffPushView

        if action == "test":
            from apps.notifications import webpush

            if not webpush.enabled():
                return Response({"detail": "browser push is not configured", "code": "disabled"}, status=503)
            n = webpush.push_to_staff(None, "🔔 تست اعلان · Test notification", "caspintunel", url="/my-groups/notifications",
                                      tag="test", staff_ids=[request.user.id])
            return Response({"ok": bool(n), "sent": n, "message": f"Test sent to {n} browser(s)",
                             "message_fa": f"اعلان آزمایشی به {n} مرورگر فرستاده شد"})
        return StaffPushView.post(self, request, action)


class ManagerForbiddenView(_Mgr):
    """Everything else a manager might try (set-limit, remove-limit, reduce, unlimited, delete
    admins, roles, prices, payments, other endpoints) — an explicit 403, never a 404."""

    def _no(self, request, *args, **kwargs):
        raise M.forbidden()

    get = post = put = patch = delete = _no


def _safe(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "-_") or "admin"
