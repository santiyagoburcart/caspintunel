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

from django.db import transaction
from django.db.models import Q
from django.http import Http404
from rest_framework import status
from rest_framework.response import Response

from apps.agency.billing import BillingError

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
        "portal_enabled": bool(get_setting("agency_portal_enabled", False)),
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
        # v1.54 «بایگانی»: ?archived=1 → only archived («حذف‌شده») admins; default → active ones (the default manager)
        archived = str(p.get("archived") or "") in ("1", "true", "yes")
        qs = PanelAdmin.all_objects.filter(archived_at__isnull=False) if archived else PanelAdmin.objects.all()
        if p.get("search"):
            qs = qs.filter(username__icontains=p["search"].strip())
        if p.get("limit") == "limited":
            qs = qs.filter(has_data_limit=True, admin_limit_bytes__gt=0)
        elif p.get("limit") == "unlimited":
            qs = qs.filter(Q(has_data_limit=False) | Q(admin_limit_bytes__lte=0))
        groups = list(AdminGroup.objects.all())
        rows = [api.admin_row(a, groups) for a in qs]
        u = request.user
        if getattr(u, "is_superuser", False) or (hasattr(u, "has_perm") and isinstance(getattr(u, "is_superadmin", None), bool)
                                                and u.has_perm("agency.accounting")):
            from apps.agency.ledger import balances

            bal = balances()
            for r in rows:
                r["balance"] = bal.get(r["username"], 0)
        if p.get("status"):
            rows = [r for r in rows if r["status_code"] == p["status"]]
        if p.get("group"):
            rows = [r for r in rows if any(str(g["id"]) == p["group"] for g in r["groups"])]
        return Response({"count": len(rows), "results": rows, "archived_count": PanelAdmin.all_objects.filter(
            archived_at__isnull=False).count(), "groups": [
            {"id": g.id, "owner": g.owner_username, "name": g.name or g.owner_username} for g in groups]})


class AgencyAdminDetailView(AdminAPIView):
    perms_map = {"GET": VIEW}

    def get(self, request, username):
        a = PanelAdmin.all_objects.filter(username=username).first()        # v1.54: archived admins keep their page
        if a is None:
            raise Http404
        return Response({**api.admin_detail(a), "switches": _switches()})


class AgencyLimitHistoryView(AdminAPIView):
    """Every data-limit change of one admin: our panel and PasarGuard directly (agency/limit_history.py)."""

    perms_map = {"GET": VIEW}

    def get(self, request, username):
        from apps.agency import limit_history

        return Response({"username": username, "results": limit_history.history(username)})


class AgencyAdminActionView(AdminAPIView):
    perms_map = {"POST": MANAGE}
    ACTIONS = {"set-limit", "remove-limit", "admin-action", "reset-deleted-traffic"}

    def post(self, request, username, action):
        if action not in self.ACTIONS:
            raise Http404
        a = PanelAdmin.objects.filter(username=username).first()
        if a is None:
            from apps.agency.archive import Archived, is_archived

            if is_archived(username):                                       # v1.54: nothing changes on the panel
                return Response({"detail": Archived.en, "detail_fa": Archived.fa, "code": "archived"}, status=409)
            raise Http404
        d = request.data
        if action == "set-limit":
            r = _run(request, "agency.set_limit", a, actions.set_limit, username, d.get("action"), d.get("value_gb"),
                     getattr(request.user, "username", ""))
            if r.status_code == 200:
                a.refresh_from_db()
                r.data["new_limit_bytes"] = a.admin_limit_bytes
                label = actions.gb_label(a.admin_limit_bytes)
                r.data["message_fa"] = ("سقف ادمین برداشته شد (نامحدود)" if label == "Unlimited"
                                        else f"سقف ادمین روی {label} تنظیم شد")
            return r
        if action == "remove-limit":
            return _run(request, "agency.remove_limit", a, actions.remove_limit, username,
                        getattr(request.user, "username", ""))
        if action == "admin-action":
            return _run(request, f"agency.{d.get('action')}", a, actions.admin_action, username, d.get("action"))
        return _run(request, "agency.reset_deleted_traffic", a, actions.reset_deleted_traffic, username)


class AgencySyncNowView(AdminAPIView):
    perms_map = {"POST": MANAGE}

    def post(self, request):
        return _run(request, "agency.sync_now", None, actions.sync_now)


class AgencyGroupsView(AdminAPIView):
    """Account groups (PAMP). GET list · POST create · PUT <id> update (rename, owner,
    members, note) · DELETE <id>."""
    perms_map = {"GET": VIEW, "POST": MANAGE, "PUT": MANAGE, "DELETE": MANAGE}

    def get(self, request, group_id=None):
        return Response({"results": api.group_rows()})

    def _save(self, request, group_id, audit_action):
        from apps.agency import groups

        d = request.data
        try:
            g = groups.upsert(group_id, owner=d.get("owner"), members=d.get("members"),
                              name=d.get("name", ""), note=d.get("note", ""))
        except actions.PreCutover as exc:
            return Response({"detail": str(exc), "code": "pre_cutover"}, status=status.HTTP_409_CONFLICT)
        except groups.GroupError as exc:
            code, _, extra = str(exc).partition(":")
            return Response({"code": code, "detail": code, "usernames": [u for u in extra.split(",") if u]},
                            status=status.HTTP_404_NOT_FOUND if code == "not_found" else status.HTTP_400_BAD_REQUEST)
        write_audit(action=audit_action, staff=request.user, target=g,
                    detail={"owner": g.owner_username, "members": g.get_members(), "name": g.name})
        return Response({"ok": True, "id": g.id}, status=status.HTTP_201_CREATED if group_id is None else 200)

    def post(self, request, group_id=None):
        return self._save(request, None, "agency.group_created")

    def put(self, request, group_id=None):
        return self._save(request, group_id, "agency.group_updated")

    def delete(self, request, group_id=None):
        from apps.agency import groups
        from apps.agency.models import AdminGroup

        g = AdminGroup.objects.filter(pk=group_id).first()
        try:
            if not g or not groups.delete(group_id):
                return Response({"code": "not_found", "detail": "not_found"}, status=status.HTTP_404_NOT_FOUND)
        except actions.PreCutover as exc:
            return Response({"detail": str(exc), "code": "pre_cutover"}, status=status.HTTP_409_CONFLICT)
        write_audit(action="agency.group_deleted", staff=request.user, target=g,
                    detail={"owner": g.owner_username, "members": g.get_members(), "name": g.name})
        return Response(status=status.HTTP_204_NO_CONTENT)


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
            return Response({"sync_enabled": ["confirm that the previous sync is stopped"]}, status=400)
        try:
            minutes = int(d.get("sync_interval_minutes", cur["sync_interval_minutes"]))
        except (TypeError, ValueError):
            return Response({"sync_interval_minutes": ["a whole number of minutes"]}, status=400)
        if not 1 <= minutes <= 1440:
            return Response({"sync_interval_minutes": ["1–1440 minutes"]}, status=400)
        set_setting("agency_sync_enabled", sync, ValueType.BOOL)
        set_setting("agency_enforcement_enabled", enforce, ValueType.BOOL)
        set_setting("agency_sync_interval_minutes", minutes, ValueType.INT)
        if "portal_enabled" in d:
            set_setting("agency_portal_enabled", bool(d.get("portal_enabled")), ValueType.BOOL)
        _reschedule(minutes)
        write_audit(action="agency.settings", staff=request.user, target=None,
                    detail={"sync_enabled": sync, "enforcement_enabled": enforce, "interval": minutes,
                            "portal_enabled": d.get("portal_enabled")})
        return Response(_switches())


def _reschedule(minutes: int) -> None:
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    sched, _ = IntervalSchedule.objects.get_or_create(every=minutes, period=IntervalSchedule.MINUTES)
    for t in PeriodicTask.objects.filter(name="agency: sync panel admins (PAMP)"):
        if t.interval_id != sched.id:
            t.interval = sched
            t.save()          # save() (not update) so django-celery-beat picks the change up


# ------------------------------------------------------------------ accounting ledger (agency.accounting)
ACCOUNTING = ["agency.accounting"]


def _date(value, field="date"):
    from datetime import date

    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        raise _Bad({field: ["use YYYY-MM-DD"]})


class _Bad(Exception):
    def __init__(self, payload):
        self.payload = payload


class AgencyLedgerOverviewView(AdminAPIView):
    """GET agency/ledger/ — v1.58 «حسابداری»: the one table + the summary strip (apps/agency/accounting.py).

    ?period=month|prev|d7|custom &from= &to= · ?tab=debtors|all · ?group=<id> · ?q= · ?sort=username|group|sales|paid|debt|
    last_payment|open_invoices &dir=asc|desc · ?page= &page_size= (default 25). Old `debtors=1` = tab debtors."""
    perms_map = {"GET": ACCOUNTING}

    def get(self, request):
        from apps.agency import accounting

        q = request.query_params
        tab = q.get("tab") or ("debtors" if str(q.get("debtors") or "") in ("1", "true") else "debtors")
        try:
            return Response(accounting.table(
                period=q.get("period") or "month", frm=q.get("from"), to=q.get("to"), tab=tab, q=q.get("q") or "",
                group=q.get("group"), sort=q.get("sort") or "debt", desc=(q.get("dir") or "desc") != "asc",
                page=int(q.get("page") or 1), size=int(q.get("page_size") or 25)))
        except accounting.history.HistoryError as exc:
            return Response({"detail": exc.en, "detail_fa": exc.fa, "field": exc.field}, status=400)
        except ValueError as exc:
            return Response({"detail": str(exc), "detail_fa": "مقدار نامعتبر"}, status=400)


class AgencyLedgerView(AdminAPIView):
    """GET statement · POST {price_per_gb, valid_from, note} to …/prices/ · POST entries to …/entries/"""
    perms_map = {"GET": ACCOUNTING, "POST": ACCOUNTING}

    def get(self, request, username):
        from apps.agency import ledger

        st = ledger.statement(username)
        n = request.query_params.get("recent")           # v1.58 the «حسابداری» drawer: only the last N entries
        if n and str(n).isdigit():
            st["entries_total"] = len(st["entries"])
            st["entries"] = st["entries"][-max(1, min(50, int(n))):]
            st["prices"] = st["prices"][:1]
        return Response(st)

    def post(self, request, username, what):
        from apps.agency import ledger

        d, by = request.data, request.user.username
        try:
            if what == "prices":
                p = ledger.set_price(username, d.get("price_per_gb"), _date(d.get("valid_from"), "valid_from") or ledger.today(),
                                     d.get("note", ""), by)
                write_audit(action="agency.price_set", staff=request.user, target=None,
                            detail={"admin": username, "price_per_gb": str(p.price_per_gb), "valid_from": str(p.valid_from)})
            elif what == "entries":
                e = ledger.add_entry(username, d.get("kind"), d.get("amount"), _date(d.get("date")) or ledger.today(),
                                     method=d.get("method", ""), note=d.get("note", ""), by=by, gb=d.get("gb"),
                                     direction=d.get("direction"), settle=d.get("settle") or None,
                                     invoice_ids=d.get("invoice_ids") or None)
                write_audit(action=f"agency.ledger_{e.kind}", staff=request.user, target=e,
                            detail={"admin": username, "amount": str(e.amount), "settle": d.get("settle") or "auto",
                                    "settles": [f"INV-{a.invoice_id:06d}:{a.amount}" for a in e.allocations.all()]})
            else:
                raise Http404
        except _Bad as exc:
            return Response(exc.payload, status=400)
        except BillingError as exc:              # v1.34: no price per GB → no charge
            return Response(exc.payload(), status=exc.status)
        except (ValueError, ArithmeticError) as exc:
            return Response({"detail": str(exc) or "invalid value"}, status=400)
        except Exception as exc:  # noqa: BLE001 — e.g. decimal.InvalidOperation on garbage input
            if exc.__class__.__name__ == "InvalidOperation":
                return Response({"detail": "invalid number"}, status=400)
            raise
        return Response(ledger.statement(username), status=201)


class AgencyLedgerVoidView(AdminAPIView):
    perms_map = {"POST": ACCOUNTING}

    def post(self, request, entry_id):
        from apps.agency import ledger
        from apps.agency.models import LedgerEntry

        try:
            e = ledger.void(entry_id, request.data.get("reason", ""), request.user.username)
        except LedgerEntry.DoesNotExist:
            raise Http404
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        write_audit(action="agency.ledger_void", staff=request.user, target=e, detail={"reason": e.void_reason})
        return Response(ledger.statement(e.admin_username))


def _jdate_param(v):
    """ISO (2026-10-21) or Jalali (1405/07/29) → date; None when missing/invalid."""
    import datetime as _dt

    import jdatetime

    if not v:
        return None
    v = str(v).strip()
    try:
        if "/" in v:
            y, m, d = (int(x) for x in v.split("/"))
            return jdatetime.date(y, m, d).togregorian() if y < 1700 else _dt.date(y, m, d)
        return _dt.date.fromisoformat(v)
    except (ValueError, TypeError):
        return None


def _export(rows, fmt, name, lang):
    from django.http import HttpResponse

    from apps.agency import reports
    from apps.common import xlsx

    if fmt == "xlsx":
        resp = HttpResponse(xlsx.build(rows, sheet=name, rtl=lang == "fa", widths=[22] + [18] * (len(rows[0]) - 1)),
                            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        resp["Content-Disposition"] = f'attachment; filename="{name}.xlsx"'
    else:
        resp = HttpResponse(reports.to_csv(rows), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{name}.csv"'
    return resp


class AgencyLedgerReportView(AdminAPIView):
    """Accounting reports from the ledger (read-only).
    GET report/overview/?from=&to=  ·  report/monthly/[?export=csv|xlsx]  ·  report/monthly/<jy>/<jm>/[?export=]"""
    perms_map = {"GET": ACCOUNTING}

    def get(self, request, what, jy=None, jm=None):
        import datetime as _dt

        from apps.agency import reports

        lang = "en" if request.query_params.get("lang") == "en" else "fa"
        fmt = request.query_params.get("export")          # not "format": DRF reserves it
        if what == "overview":
            from apps.common.jalali import tehran_today

            today = tehran_today()
            frm = _jdate_param(request.query_params.get("from")) or today.replace(day=1)
            to = _jdate_param(request.query_params.get("to")) or today
            if frm > to:
                frm, to = to, frm
            if (to - frm).days > 3660:
                return Response({"detail": "range too long (max 10 years)"}, status=400)
            return Response(reports.overview(frm, to))
        if what == "monthly" and jy is None:
            if fmt in ("csv", "xlsx"):
                return _export(reports.monthly_rows(lang), fmt, "agency-monthly", lang)
            return Response({"results": reports.monthly()})
        if what == "monthly":
            if not (1300 <= int(jy) <= 1600 and 1 <= int(jm) <= 12):
                return Response({"detail": "invalid month"}, status=400)
            if fmt in ("csv", "xlsx"):
                return _export(reports.breakdown_rows(int(jy), int(jm), lang), fmt, f"agency-{jy}-{int(jm):02d}", lang)
            return Response(reports.month_breakdown(int(jy), int(jm)))
        return Response({"detail": "not found"}, status=404)


class AgencyLedgerExportView(AdminAPIView):
    perms_map = {"GET": ACCOUNTING}

    def get(self, request, username):
        from django.http import HttpResponse

        from apps.agency import ledger

        resp = HttpResponse(ledger.statement_csv(username), content_type="text/csv; charset=utf-8")
        safe = "".join(c for c in username if c.isalnum() or c in "-_") or "admin"
        resp["Content-Disposition"] = f'attachment; filename="statement-{safe}.csv"'
        return resp


# ------------------------------------------------------------------ admin / portal paths (docs/paths.md)
class PathsView(AdminAPIView):
    """GET applied paths + pending request + last result · POST {admin, portal} → request
    (applied by the host watcher within a minute). Superadmins only."""
    perms_map = {"GET": ["settings.manage"], "POST": ["settings.manage"]}

    def _superadmin(self, request):
        return getattr(request.user, "is_superadmin", False) or getattr(request.user, "is_superuser", False)

    def get(self, request):
        from apps.settings_app import paths

        return Response(paths.state())

    def post(self, request):
        from apps.settings_app import paths

        if not self._superadmin(request):
            return Response({"detail": "only a super admin can move the panel"}, status=403)
        cur = paths.state()
        admin = (request.data.get("admin") or cur["admin"]).strip().rstrip("/").lower()
        portal = (request.data.get("portal") or cur["portal"]).strip().rstrip("/").lower()
        errors = paths.validate(admin, portal)
        if errors:
            return Response(errors, status=400)
        if admin == cur["admin"] and portal == cur["portal"]:
            return Response({**cur, "detail": "nothing to change"})
        req = paths.request_change(admin, portal, request.user.username)
        write_audit(action="paths.change_requested", staff=request.user, target=None, detail=req)
        return Response(paths.state(), status=202)


class AgencySetLimitPreviewView(AdminAPIView):
    """POST {action, value_gb} → what the change WOULD do (no panel call, nothing saved)."""
    perms_map = {"POST": MANAGE}

    def post(self, request, username):
        try:
            return Response(actions.preview_set_limit(username, request.data.get("action"), request.data.get("value_gb")))
        except ValueError as exc:
            return Response({"value_gb": [str(exc)]}, status=400)


class AgencyPortalLinkView(AdminAPIView):
    """GET → {path, url}; GET …/qr.png → plain QR of the url."""
    perms_map = {"GET": VIEW}

    def get(self, request, fmt=None):
        link = api.portal_link()
        if fmt == "png":
            from django.http import HttpResponse

            from apps.common import qrcard

            img, _ = qrcard.compose(link["url"], None)
            resp = HttpResponse(qrcard.to_png(img), content_type="image/png")
            resp["Cache-Control"] = "private, no-store"
            return resp
        return Response(link)


# --- PasarGuard admin create / edit / delete (apps/agency/admin_crud.py) ---------------
def _crud_error(exc):
    from apps.agency.admin_crud import AdminCrudError

    if isinstance(exc, actions.PreCutover):
        return Response({"detail": str(exc), "code": "pre_cutover"}, status=status.HTTP_409_CONFLICT)
    if isinstance(exc, AdminCrudError):
        code = 409 if exc.code == "exists" else 404 if exc.code == "not_found" else \
            502 if exc.code in ("panel_error", "panel_refused") else 400
        body = {"detail": str(exc), "code": exc.code, "field": exc.field}
        if getattr(exc, "message_fa", None):
            body["detail_fa"] = exc.message_fa
        return Response(body, status=code)
    raise exc


class AgencyPanelAdminOptionsView(AdminAPIView):
    """Panels to create on + the chosen panel's roles (with the groups / templates
    each role allows) read live from PasarGuard."""
    perms_map = {"GET": MANAGE}

    def get(self, request):
        from apps.agency import admin_crud as C

        try:
            panel = C.panel_for(request.query_params.get("panel"))
            opts = C.options(panel)
        except Exception as exc:  # noqa: BLE001
            return _crud_error(exc)
        return Response({
            "panels": [{"id": p.id, "name": p.name, "agency": C.is_agency_panel(p)} for p in C.panels()],
            "panel": panel.id, **opts,
            "agency_groups": [{"id": g.id, "name": g.name or g.owner_username, "owner": g.owner_username}
                              for g in AdminGroup.objects.order_by("owner_username")],
            "writes_enabled": actions.writes_enabled(),
        })


class AgencyPanelAdminCreateView(AdminAPIView):
    perms_map = {"POST": MANAGE}

    def post(self, request):
        from apps.agency import admin_crud as C

        data = request.data or {}
        if data.get("price_per_gb") not in (None, "") and not request.user.has_perm("agency.accounting"):
            return Response({"detail": "setting a price needs agency.accounting", "code": "forbidden"}, status=403)
        try:
            panel = C.panel_for(data.get("panel"))
            out = C.create(panel, data, by=request.user.username)
        except Exception as exc:  # noqa: BLE001
            return _crud_error(exc)
        write_audit(action="agency.admin_created", staff=request.user, target=None, detail={
            "username": out["username"], "panel": panel.name, "role_id": data.get("role_id"),
            "limit_bytes": out["limit_bytes"], "charge": out["charge"], "group": out["group"]})   # never the password
        return Response({**out, "ok": True, "message": f"Admin {out['username']} created",
                         "message_fa": f"ادمین {out['username']} ساخته شد"}, status=201)


class AgencyPanelAdminView(AdminAPIView):
    perms_map = {"GET": MANAGE, "PATCH": MANAGE, "DELETE": MANAGE}

    def get(self, request, username):
        from apps.agency import admin_crud as C

        try:
            panel = C.panel_for(request.query_params.get("panel"))
            return Response(C.editable_view(C.get_admin(panel, username)))
        except Exception as exc:  # noqa: BLE001
            return _crud_error(exc)

    def patch(self, request, username):
        from apps.agency import admin_crud as C

        data = request.data or {}
        try:
            panel = C.panel_for(data.get("panel"))
            out = C.modify(panel, username, data)
        except Exception as exc:  # noqa: BLE001
            return _crud_error(exc)
        write_audit(action="agency.admin_updated", staff=request.user, target=None,
                    detail={"username": username, "panel": panel.name, "fields": out["changed"],
                            "password_reset": out["password_changed"]})
        return Response({**out, "ok": True, "message": "Admin settings saved on the panel",
                         "message_fa": "تنظیمات ادمین روی پنل ذخیره شد"})

    def delete(self, request, username):
        from apps.agency import admin_crud as C

        data = request.data or {}
        try:
            panel = C.panel_for(data.get("panel") or request.query_params.get("panel"))
            C.delete(panel, username, data.get("confirm") or request.query_params.get("confirm", ""),
                     by=getattr(request.user, "username", ""))
        except Exception as exc:  # noqa: BLE001
            return _crud_error(exc)
        write_audit(action="agency.admin_deleted", staff=request.user, target=None,
                    detail={"username": username, "panel": panel.name})
        return Response({"ok": True, "message": f"Admin {username} deleted on the panel — archived here (accounting and history kept)",
                         "message_fa": f"ادمین {username} حذف شد و به «بایگانی» رفت — حساب، فاکتورها و سابقه‌اش محفوظ است"})


class AgencyStoreView(AdminAPIView):
    """v1.43 (multi-tenant Phase 2, D5) «فروشگاه» on an agency admin's page — our staff only (never on a store's domain):
    GET the admin's store (or null), POST {name} opens it (draft), PATCH {name, status, export_allowed}. Domains (Phase 3)
    and the bot (Phase 6) come later; without an active domain the store is not reachable."""

    perms_map = {"GET": VIEW, "POST": MANAGE, "PATCH": MANAGE}

    def get(self, request, username):
        from apps.tenancy import stores

        return Response({"store": stores.row(stores.store_of(username))})

    def post(self, request, username):
        from apps.tenancy import stores

        try:
            t = stores.enable(username, name=str(request.data.get("name") or ""), staff=request.user)
        except stores.StoreError as exc:
            return Response({"detail": exc.en, "detail_fa": exc.fa}, status=exc.status)
        return Response({"store": stores.row(t), "message": f"Store {t.name} opened (draft)",
                         "message_fa": f"فروشگاه {t.name} ساخته شد (پیش‌نویس)"}, status=201)

    def patch(self, request, username):
        from apps.tenancy import stores

        t = stores.store_of(username)
        if t is None:
            return Response({"detail": "this admin has no store", "detail_fa": "این ادمین فروشگاه ندارد"}, status=404)
        try:
            t = stores.update(t, request.data or {}, staff=request.user)
        except stores.StoreError as exc:
            return Response({"detail": exc.en, "detail_fa": exc.fa}, status=exc.status)
        return Response({"store": stores.row(t), "message": "Store saved", "message_fa": "فروشگاه ذخیره شد"})


def _store_or_404(username):
    from apps.tenancy import stores

    t = stores.store_of(username)
    if t is None:
        return None, Response({"detail": "this admin has no store", "detail_fa": "این ادمین فروشگاه ندارد"}, status=404)
    return t, None


def _domain_error(exc):
    return Response({"detail": exc.en, "detail_fa": exc.fa, "field": exc.field}, status=exc.status)


class AgencyStoreDomainsView(AdminAPIView):
    """v1.45 (Phase 3) POST {host, mode: direct|tunnel, www} — add a domain to the admin's store (our staff only, D5). The
    answer carries the exact records to give the reseller (A to our Finland / Iran IP, www, TXT verification)."""

    perms_map = {"POST": MANAGE}

    def post(self, request, username):
        from apps.tenancy import domains, stores

        t, err = _store_or_404(username)
        if err:
            return err
        data = request.data or {}
        try:
            d = domains.add(t, str(data.get("host") or ""), mode=str(data.get("mode") or "direct"),
                            include_www=str(data.get("www", True)).lower() not in ("0", "false", "no", "off"),
                            staff=request.user)
        except domains.DomainError as exc:
            return _domain_error(exc)
        return Response({"store": stores.row(t), "domain": domains.row(d),
                         "message": f"{d.host} added — send the reseller the records shown",
                         "message_fa": f"دامنهٔ {d.host} اضافه شد — رکوردهای نمایش داده‌شده را به نماینده بدهید"}, status=201)


class AgencyStoreBotView(AdminAPIView):
    """v1.49 (Phase 6, D5) the store's own Telegram bot — our staff only: POST {token} sets / replaces it (getMe, webhook,
    menu button → the store's Mini App), DELETE removes it (webhook deleted). The token is never sent back."""

    perms_map = {"POST": MANAGE, "DELETE": MANAGE}

    def post(self, request, username):
        from apps.tenancy import bots, stores

        t, err = _store_or_404(username)
        if err:
            return err
        try:
            b = bots.set_token(t, str((request.data or {}).get("token") or ""), staff=request.user)
        except bots.BotError as exc:
            return Response({"detail": exc.en, "detail_fa": exc.fa, "field": "token", "code": exc.key}, status=exc.status)
        t.refresh_from_db()
        ok = b.state == b.OK
        return Response({"store": stores.row(t),
                         "message": f"@{b.username} connected" if ok else f"@{b.username} saved, but: {b.last_error}",
                         "message_fa": f"ربات @{b.username} وصل شد" if ok else f"ربات @{b.username} ذخیره شد ولی: {b.last_error}"},
                        status=200 if ok else 202)

    def delete(self, request, username):
        from apps.tenancy import bots, stores

        t, err = _store_or_404(username)
        if err:
            return err
        bots.remove(t, staff=request.user)
        t.refresh_from_db()
        return Response({"store": stores.row(t), "message": "Store bot removed", "message_fa": "ربات فروشگاه حذف شد"})


class AgencyStoreBotCheckView(AdminAPIView):
    """v1.49 POST — «بررسی ربات»: getWebhookInfo now; a wrong webhook / menu button is set again."""

    perms_map = {"POST": MANAGE}

    def post(self, request, username):
        from apps.tenancy import bots, stores
        from apps.tenancy.models import TenantBot

        t, err = _store_or_404(username)
        if err:
            return err
        b = TenantBot.objects.filter(tenant=t).first()
        if b is None:
            return Response({"detail": "this store has no bot", "detail_fa": "این فروشگاه ربات ندارد"}, status=404)
        b = bots.apply(b) if str((request.data or {}).get("apply", "")).lower() in ("1", "true") else bots.check(b)
        t.refresh_from_db()
        return Response({"store": stores.row(t),
                         "message": "Bot OK" if b.state == b.OK else f"Bot error: {b.last_error}",
                         "message_fa": "ربات سالم است" if b.state == b.OK else f"خطای ربات: {b.last_error}"})


class AgencyStoreCeilingView(AdminAPIView):
    """v1.52 (Phase 8) PUT {codes: [...]} — the permission codes this store's staff may hold and grant (⊆ STORE_CODES; our staff
    only). Lowering it strips the codes from the store's roles at once; the owner's role always equals it."""

    perms_map = {"PUT": MANAGE}

    def put(self, request, username):
        from apps.tenancy import staff as S
        from apps.tenancy import stores

        t, err = _store_or_404(username)
        if err:
            return err
        try:
            S.set_ceiling(t, (request.data or {}).get("codes") or [], staff=request.user)
        except S.StaffError as exc:
            return Response({"detail": exc.en, "detail_fa": exc.fa, "field": exc.field}, status=exc.status)
        t.refresh_from_db()
        return Response({"store": stores.row(t), "message": "Store permissions saved", "message_fa": "سقف دسترسی فروشگاه ذخیره شد"})


class AgencyStoreOwnerView(AdminAPIView):
    """v1.52 (Phase 8) POST {username} — create the store owner's login (first time) or reset its password (then: no body
    needed). The password is in this answer ONCE — never stored in clear, never audited."""

    perms_map = {"POST": MANAGE}

    def post(self, request, username):
        from apps.tenancy import staff as S
        from apps.tenancy import stores

        t, err = _store_or_404(username)
        if err:
            return err
        try:
            owner, password = S.ensure_owner(t, str((request.data or {}).get("username") or ""), staff=request.user)
        except S.StaffError as exc:
            return Response({"detail": exc.en, "detail_fa": exc.fa, "field": exc.field}, status=exc.status)
        t.refresh_from_db()
        return Response({"store": stores.row(t), "owner": owner.username, "password": password,
                         "message": f"Owner login {owner.username} ready — copy the password now",
                         "message_fa": f"ورود مالک فروشگاه ({owner.username}) آماده است — رمز را همین حالا کپی کنید"})


class AgencyStoreFailedOrdersView(AdminAPIView):
    """v1.52.1 GET — the store's «ساخت ناموفق» orders on our «فروشگاه» card (our staff only, read inside the store)."""

    perms_map = {"GET": MANAGE}

    def get(self, request, username):
        from apps.tenancy import context, failed_orders

        t, err = _store_or_404(username)
        if err:
            return err
        with context.tenant_context(t.pk):
            return Response({"results": failed_orders.rows(), "count": failed_orders.count()})


class AgencyStoreFailedOrderRetryView(AdminAPIView):
    """v1.52.1 POST {account_name?} — our staff retry a store's failed order (same paid order, in the store's context:
    the account goes to the reseller's admin as always; the store's staff see the result in their panel)."""

    perms_map = {"POST": MANAGE}

    def post(self, request, username, pk):
        from apps.tenancy import context, failed_orders

        t, err = _store_or_404(username)
        if err:
            return err
        with context.tenant_context(t.pk):
            try:
                out = failed_orders.retry(pk, request.user, (request.data or {}).get("account_name"))
            except failed_orders.RetryError as exc:
                return Response(exc.payload(), status=exc.status)
        return Response(out)


class AgencyStoreDomainView(AdminAPIView):
    """v1.45 PATCH {mode?, www?} · DELETE (remove: nginx file + certificate go, the store stops answering on it)."""

    perms_map = {"PATCH": MANAGE, "DELETE": MANAGE}

    def _get(self, username, pk):
        from apps.tenancy.models import TenantDomain

        t, err = _store_or_404(username)
        if err:
            return None, None, err
        d = TenantDomain.objects.filter(pk=pk, tenant=t).exclude(state=TenantDomain.REMOVED).first()
        if d is None:
            return None, None, Response({"detail": "domain not found", "detail_fa": "دامنه پیدا نشد"}, status=404)
        return t, d, None

    def patch(self, request, username, pk):
        from apps.tenancy import domains, stores

        t, d, err = self._get(username, pk)
        if err:
            return err
        data = request.data or {}
        www = data.get("www")
        try:
            d = domains.update(d, mode=data.get("mode"), staff=request.user,
                               include_www=None if www is None else str(www).lower() not in ("0", "false", "no", "off"))
        except domains.DomainError as exc:
            return _domain_error(exc)
        return Response({"store": stores.row(t), "message": f"{d.host} saved", "message_fa": f"دامنهٔ {d.host} ذخیره شد"})

    def delete(self, request, username, pk):
        from apps.tenancy import domains, stores

        t, d, err = self._get(username, pk)
        if err:
            return err
        domains.remove(d, staff=request.user)
        return Response({"store": stores.row(t), "message": f"{d.host} removed", "message_fa": f"دامنهٔ {d.host} حذف شد"})


class AgencyStoreDomainCheckView(AgencyStoreDomainView):
    """v1.45 POST — «بررسی الان / تلاش دوباره»: DNS again now; a failed certificate gets fresh attempts."""

    perms_map = {"POST": MANAGE}

    def post(self, request, username, pk):
        from apps.tenancy import domains, stores
        from apps.tenancy.tasks import store_domain_check_task

        t, d, err = self._get(username, pk)
        if err:
            return err
        try:
            d = domains.retry(d, staff=request.user)
        except domains.DomainError as exc:
            return _domain_error(exc)
        transaction.on_commit(lambda: store_domain_check_task.delay(d.pk))
        return Response({"store": stores.row(t), "message": f"Checking {d.host} now",
                         "message_fa": f"بررسی {d.host} شروع شد — نتیجه تا یک دقیقه دیگر"})


class AgencyHistoryView(AdminAPIView):
    """v1.54 «تاریخچه» — our staff: ?scope=all|group|admin &group= &admin= &period=d7|month|prev|custom &from= &to=
    &export=csv|xlsx. Built from the ledger / invoices (immutable), never reset by settlement, payments or adjustments;
    archived («حذف‌شده») admins included."""

    perms_map = {"GET": ACCOUNTING}

    def get(self, request):
        from apps.agency import history as H
        from apps.agency.reports import export_response

        q = request.query_params
        scope = q.get("scope") or ("admin" if q.get("admin") else "group" if q.get("group") else "all")
        groups = list(AdminGroup.objects.order_by("owner_username"))
        if scope == "admin":
            if not q.get("admin"):
                return Response({"detail": "pick an admin", "detail_fa": "ادمین را انتخاب کنید", "field": "admin"}, status=400)
            names, sc = [q["admin"]], {"kind": "admin", "admin": q["admin"]}
        elif scope == "group":
            g = next((x for x in groups if str(x.id) == str(q.get("group"))), None)
            if g is None:
                return Response({"detail": "unknown group", "detail_fa": "گروه پیدا نشد", "field": "group"}, status=400)
            names, sc = g.get_all_usernames(), {"kind": "group", "group": g.id, "name": g.name or g.owner_username}
        else:
            names, sc = H.all_usernames(), {"kind": "all"}
        try:
            rep = H.report(names, q.get("period") or "month", q.get("from"), q.get("to"), scope=sc)
        except H.HistoryError as exc:
            return Response(exc.payload(), status=400)
        lang = "en" if q.get("lang") == "en" else "fa"
        if q.get("export") in ("csv", "xlsx"):
            return export_response(H.export_rows(rep, lang), q["export"], "agency-history", lang)
        return Response({**rep, "groups": [{"id": g.id, "name": g.name or g.owner_username} for g in groups],
                         "admins_list": H.all_usernames()})
