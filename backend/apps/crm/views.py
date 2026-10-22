"""CRM staff API under /api/v1/admin/crm/ — reads need `crm.view`, writes `crm.manage`.

customers/<id>/            GET 360 · PATCH {owner, stage_override, tags}
customers/<id>/timeline/   GET merged activity (orders, payments, tickets, notifications, CRM events)
customers/<id>/notes/      POST {body}
customers/<id>/cases/      POST {kind: manual|lead, notes}
customers/<id>/message/    POST {template?, body_fa?, body_en?, via_site, via_bot, via_email}
cases/                     GET queue (?status=open|closed&kind=&reason=&assigned=me|none|<id>&q=&offset=)
cases/<id>/                GET · PATCH {reason, notes, assigned_to}
cases/<id>/close/          POST {outcome, note}
cases/<id>/message/        POST like customers/<id>/message/
cases/<id>/ticket/         POST {topic, subject, body} — opens a ticket for the customer, linked to the case
leads/                     GET never-purchased users (?q=&offset=)
reports/                   GET ?days=7|30|90|0
settings/ · reasons/ · templates/ · tags/
"""
from __future__ import annotations

import statistics
from datetime import timedelta

from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response

from apps.accounts.models import Staff, User
from apps.adminpanel.views.base import AdminAPIView
from apps.common.models import write_audit
from apps.settings_app.models import ValueType
from apps.settings_app.utils import set_setting

from . import services as S
from .models import (
    CaseKind,
    CaseReason,
    CaseStatus,
    CrmEvent,
    CustomerNote,
    EventKind,
    FollowUpCase,
    MessageTemplate,
    Stage,
    Tag,
)

VIEW, MANAGE = ["crm.view"], ["crm.manage"]
PAGE = 50


def _err(exc):
    from apps.tickets.services import TicketError

    from .retention import RetentionError

    if isinstance(exc, (S.CrmError, TicketError, RetentionError)):
        return Response({"detail": str(exc), "code": exc.code}, status=exc.status)
    raise exc


def _staff_row(s):
    return {"id": s.id, "username": s.username, "display_name": s.display_name} if s else None


def _truthy(v) -> bool:
    return v is True or str(v).lower() in ("1", "true", "yes", "on")


class _Staff(AdminAPIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not isinstance(request.user, Staff):
            self.permission_denied(request, message="log in with a staff account")


def _customer(pk) -> User:
    return get_object_or_404(User, pk=pk)


def _profile_row(p) -> dict:
    return {"stage": p.stage, "stage_override": p.stage_override, "effective_stage": p.effective_stage,
            "stage_changed_at": p.stage_changed_at, "owner": _staff_row(p.owner),
            "tags": [{"id": t.id, "name": t.name, "color": t.color} for t in p.tags.all()]}


def _service_row(s) -> dict:
    return {"id": s.id, "panel_username": s.panel_username, "status": s.status, "data_used": s.data_used,
            "data_limit": s.data_limit, "expire_at": s.expire_at, "online_at": s.online_at, "last_synced_at": s.last_synced_at,
            "created_at": s.created_at, "plan": s.current_plan.name_fa if s.current_plan else None,
            "plan_en": s.current_plan.name_en if s.current_plan else None}


def case_row(c) -> dict:
    u = c.user
    plan = c.service.current_plan if c.service and c.service.current_plan_id else None
    return {
        "plan": {"name_fa": plan.name_fa, "name_en": plan.name_en} if plan else None,
        "ended_at": c.ended_at, "recovered_amount": str(c.recovered_amount) if c.recovered_amount is not None else None,
        "id": c.id, "kind": c.kind, "status": c.status, "outcome": c.outcome,
        "reason": {"id": c.reason_id, "name_fa": c.reason.name_fa, "name_en": c.reason.name_en} if c.reason else None,
        "notes": c.notes, "assigned_to": _staff_row(c.assigned_to),
        "user": {"id": u.id, "username": u.username, "name": u.name, "phone": u.phone, "telegram": bool(u.telegram_id)},
        "service": _service_row(c.service) if c.service else None,
        "ticket": {"id": c.ticket_id, "number": c.ticket.number, "status": c.ticket.status} if c.ticket else None,
        "last_online_at": c.last_online_at, "inactive_since": c.inactive_since, "auto_message_at": c.auto_message_at,
        "opened_at": c.opened_at, "closed_at": c.closed_at, "closed_by": _staff_row(c.closed_by), "closed_by_system": c.closed_by_system,
    }


def _cases_qs():
    return FollowUpCase.objects.select_related("user", "service", "service__current_plan", "reason", "assigned_to", "ticket", "closed_by")


def _winback_extras(c) -> dict:
    """Queue context for a win-back item: LTV, open tickets / cases, the active discount code."""
    from .retention import active_code

    u = c.user
    code = active_code(u)
    return {"ltv": str(S.ltv(u)), "open_tickets": u.tickets.exclude(status="closed").count(),
            "open_cases": FollowUpCase.objects.filter(user=u, status=CaseStatus.OPEN).exclude(pk=c.pk).count(),
            "discount": {"code": code.code, "percent": code.percent, "expires_at": code.expires_at} if code else None}


# --- customer 360 ------------------------------------------------------------------------
class CustomerView(_Staff):
    perms_map = {"GET": VIEW, "PATCH": MANAGE}

    def get(self, request, pk):
        u = _customer(pk)
        p = S.refresh_stage(u)
        bought = u.orders.filter(status__in=S.BOUGHT)
        tickets = u.tickets.select_related("topic").order_by("-last_activity_at")
        out = {
            "user": {"id": u.id, "username": u.username, "name": u.name, "phone": u.phone, "email": u.email,
                     "telegram_id": u.telegram_id, "telegram_username": u.telegram_username, "source": u.source,
                     "language": u.language, "created_at": u.created_at, "last_login": u.last_login, "is_active": u.is_active,
                     "deleted_at": u.deleted_at, "referred_by": {"id": u.referred_by_id, "username": u.referred_by.username} if u.referred_by_id else None},
            "profile": _profile_row(p),
            "services": [_service_row(s) for s in u.services.select_related("current_plan").order_by("-id")],
            "money": {"ltv": str(S.ltv(u)), "orders": bought.count(),
                      "first_purchase": bought.order_by("created_at").values_list("created_at", flat=True).first(),
                      "last_purchase": bought.order_by("-created_at").values_list("created_at", flat=True).first()},
            "orders": [{"id": o.id, "type": o.type, "status": o.status, "amount": str(o.amount_unique or o.amount),
                        "plan": o.plan.name_fa if o.plan else None, "plan_en": o.plan.name_en if o.plan else None, "created_at": o.created_at}
                       for o in u.orders.select_related("plan").order_by("-created_at")[:10]],
            "payments": None,
            "tickets": {"count": tickets.count(), "open": tickets.exclude(status="closed").count(),
                        "rows": [{"id": t.id, "number": t.number, "subject": t.subject, "status": t.status,
                                  "topic": t.topic.name_fa, "topic_en": t.topic.name_en, "last_activity_at": t.last_activity_at}
                                 for t in tickets[:10]] if request.user.has_perm("tickets.view") else []},
            "notifications": [{"id": n.id, "title": n.title, "title_en": n.title_en, "type": n.type, "created_at": n.created_at,
                               "channels": [c for c, on in (("site", n.via_site), ("bot", n.via_bot), ("email", n.via_email)) if on]}
                              for n in u.notifications.order_by("-created_at")[:10]],
            "notes": [{"id": n.id, "body": n.body, "staff": n.staff_label, "created_at": n.created_at} for n in u.crm_notes.all()[:50]],
            "cases": [case_row(c) for c in _cases_qs().filter(user=u)[:20]],
        }
        if request.user.has_perm("payment.view"):
            from apps.payments_sms.models import Payment

            out["payments"] = [{"id": x.id, "order": x.order_id, "amount": str(x.amount), "status": x.status, "method": x.method,
                                "created_at": x.created_at} for x in Payment.objects.filter(order__user=u).order_by("-created_at")[:10]]
        return Response(out)

    def patch(self, request, pk):
        u = _customer(pk)
        p = S.profile(u)
        d = request.data or {}
        if "owner" in d:
            owner = get_object_or_404(Staff, pk=d["owner"]) if d["owner"] not in (None, "", "null") else None
            if owner != p.owner:
                p.owner = owner
                p.save(update_fields=["owner", "updated_at"])
                S.log(u, EventKind.OWNER, staff=request.user, owner=owner.username if owner else None)
        if "stage_override" in d:
            v = d["stage_override"] or ""
            if v and v not in Stage.values:
                return Response({"detail": "unknown stage", "code": "stage"}, status=400)
            if v != p.stage_override:
                old = p.effective_stage
                p.stage_override = v
                p.save(update_fields=["stage_override", "updated_at"])
                S.log(u, EventKind.STAGE, staff=request.user, old=old, new=p.effective_stage, manual=True)
        if "tags" in d:
            tags = list(Tag.objects.filter(pk__in=d.get("tags") or []))
            p.tags.set(tags)
            S.log(u, EventKind.TAGS, staff=request.user, tags=[t.name for t in tags])
        write_audit(action="crm.customer_updated", staff=request.user, target=u, detail={k: d[k] for k in ("owner", "stage_override", "tags") if k in d})
        return Response(_profile_row(p))


def timeline(u, *, limit=150) -> list:
    from apps.payments_sms.models import Payment

    items = []
    items.append({"at": u.created_at, "kind": "signup", "source": u.source})
    for o in u.orders.select_related("plan").order_by("-created_at")[:limit]:
        items.append({"at": o.created_at, "kind": "order", "order": o.id, "type": o.type, "status": o.status,
                      "amount": str(o.amount_unique or o.amount), "plan": o.plan.name_fa if o.plan else None,
                      "plan_en": o.plan.name_en if o.plan else None})
    for x in Payment.objects.filter(order__user=u).exclude(confirmed_at__isnull=True).order_by("-confirmed_at")[:limit]:
        items.append({"at": x.confirmed_at, "kind": "payment", "status": x.status, "amount": str(x.amount), "method": x.method,
                      "by": x.confirmed_by})
    for t in u.tickets.select_related("topic").order_by("-created_at")[:limit]:
        items.append({"at": t.created_at, "kind": "ticket", "ticket": t.id, "number": t.number, "subject": t.subject, "status": t.status})
        if t.closed_at:
            items.append({"at": t.closed_at, "kind": "ticket_closed", "ticket": t.id, "number": t.number, "by": t.closed_by_kind})
    for n in u.notifications.order_by("-created_at")[:limit]:
        items.append({"at": n.created_at, "kind": "notification", "title": n.title, "title_en": n.title_en})
    from .models import ServiceWarning

    for w in ServiceWarning.objects.filter(service__user=u).exclude(bot_error__startswith="skipped").select_related("service")[:limit]:
        items.append({"at": w.created_at, "kind": "warning", "warn_kind": w.kind, "threshold": w.threshold,
                      "service": w.service.panel_username, "renewed": bool(w.renewed_at),
                      "channels": [c for c, t in (("site", w.site_sent_at), ("bot", w.bot_sent_at if not w.bot_error else None),
                                                  ("email", w.email_sent_at if not w.email_error else None)) if t]})
    for e in CrmEvent.objects.filter(user=u)[:limit]:
        items.append({"at": e.created_at, "kind": "crm_" + e.kind, "actor": e.actor_label, "case": e.case_id, **e.detail})
    items.sort(key=lambda x: x["at"], reverse=True)
    return items[:limit]


class TimelineView(_Staff):
    perms_map = {"GET": VIEW}

    def get(self, request, pk):
        return Response(timeline(_customer(pk)))


class NotesView(_Staff):
    perms_map = {"POST": MANAGE}

    def post(self, request, pk):
        u = _customer(pk)
        body = str((request.data or {}).get("body") or "").strip()
        if not body:
            return Response({"detail": "the note is empty", "code": "empty"}, status=400)
        n = CustomerNote.objects.create(user=u, staff=request.user, staff_label=request.user.username, body=body[:4000])
        S.log(u, EventKind.NOTE, staff=request.user, preview=body[:140])
        return Response({"id": n.id, "body": n.body, "staff": n.staff_label, "created_at": n.created_at}, status=201)


class CustomerCaseView(_Staff):
    perms_map = {"POST": MANAGE}

    def post(self, request, pk):
        u = _customer(pk)
        kind = (request.data or {}).get("kind") or CaseKind.MANUAL
        if kind not in (CaseKind.MANUAL, CaseKind.LEAD):
            return Response({"detail": "kind must be manual or lead", "code": "kind"}, status=400)
        c = S.open_manual(u, request.user, kind=kind, notes=str((request.data or {}).get("notes") or ""))
        return Response(case_row(_cases_qs().get(pk=c.pk)), status=201)


def _send(request, user, case=None):
    d = request.data or {}
    tpl = None
    if d.get("template"):
        tpl = MessageTemplate.objects.filter(pk=d["template"]).first()
        if tpl is None:
            return Response({"detail": "unknown template", "code": "template"}, status=400)
    try:
        S.send_message(user, request.user, template=tpl if not d.get("body_fa") else None,
                       body_fa=d.get("body_fa") or "", body_en=d.get("body_en") or "", case=case,
                       via_site=_truthy(d.get("via_site", True)), via_bot=_truthy(d.get("via_bot", True)),
                       via_email=_truthy(d.get("via_email", False)))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return Response({"ok": True, "message": "Message sent", "message_fa": "پیام ارسال شد"})


class CustomerMessageView(_Staff):
    perms_map = {"POST": MANAGE}

    def post(self, request, pk):
        return _send(request, _customer(pk))


class TemplatePreviewView(_Staff):
    perms_map = {"GET": VIEW}

    def get(self, request, pk, tpl):
        u = _customer(pk)
        t = get_object_or_404(MessageTemplate, pk=tpl)
        svc = u.services.order_by("-id").first()
        fa, en = S.render(t, u, svc)
        return Response({"body_fa": fa, "body_en": en})


# --- cases ------------------------------------------------------------------------------
class CasesView(_Staff):
    perms_map = {"GET": VIEW}

    def get(self, request):
        p = request.query_params
        qs = _cases_qs()
        st = p.get("status", "open")
        if st in CaseStatus.values:
            qs = qs.filter(status=st)
        if p.get("kind"):
            qs = qs.filter(kind=p["kind"])
        else:
            qs = qs.exclude(kind=CaseKind.WINBACK)          # win-back has its own queue
        if p.get("reason"):
            qs = qs.filter(reason_id=p["reason"]) if p["reason"] != "none" else qs.filter(reason__isnull=True)
        a = p.get("assigned", "")
        if a == "me":
            qs = qs.filter(assigned_to=request.user)
        elif a == "none":
            qs = qs.filter(assigned_to__isnull=True)
        elif a.isdigit():
            qs = qs.filter(assigned_to_id=int(a))
        q = (p.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(user__username__icontains=q) | Q(user__phone__icontains=q) | Q(user__name__icontains=q)
                           | Q(service__panel_username__icontains=q))
        try:
            off = max(0, int(p.get("offset", 0)))
        except ValueError:
            off = 0
        total = qs.count()
        counts = dict(FollowUpCase.objects.filter(status=CaseStatus.OPEN).values_list("kind").annotate(n=Count("id")).values_list("kind", "n"))
        return Response({"count": total, "next": off + PAGE if off + PAGE < total else None,
                         "open_counts": {k: counts.get(k, 0) for k in CaseKind.values},
                         "results": [{**case_row(c), **(_winback_extras(c) if c.kind == CaseKind.WINBACK else {})}
                                     for c in qs.order_by("-opened_at")[off:off + PAGE]]})


class CaseView(_Staff):
    perms_map = {"GET": VIEW, "PATCH": MANAGE}

    def get(self, request, pk):
        c = get_object_or_404(_cases_qs(), pk=pk)
        return Response({**case_row(c), **(_winback_extras(c) if c.kind == CaseKind.WINBACK else {}), "events": [{"id": e.id, "kind": e.kind, "actor": e.actor_label, "detail": e.detail,
                                                     "created_at": e.created_at} for e in c.events.all()]})

    def patch(self, request, pk):
        c = get_object_or_404(_cases_qs(), pk=pk)
        d = request.data or {}
        kw = {}
        if "reason" in d:
            kw["reason_id"] = d["reason"] or None
        if "notes" in d:
            kw["notes"] = str(d["notes"] or "")
        if "assigned_to" in d:
            kw["assigned_to"] = get_object_or_404(Staff, pk=d["assigned_to"]) if d["assigned_to"] not in (None, "", "null") else None
        try:
            S.update_case(c, request.user, **kw)
        except Exception as exc:  # noqa: BLE001
            return _err(exc)
        return Response(case_row(_cases_qs().get(pk=pk)))


class CaseCloseView(_Staff):
    perms_map = {"POST": MANAGE}

    def post(self, request, pk):
        c = get_object_or_404(_cases_qs(), pk=pk)
        d = request.data or {}
        if c.reason_id is None and d.get("reason"):
            S.update_case(c, request.user, reason_id=d["reason"])
        try:
            S.close(c, request.user, d.get("outcome"), note=str(d.get("note") or "").strip())
        except Exception as exc:  # noqa: BLE001
            return _err(exc)
        return Response(case_row(_cases_qs().get(pk=pk)))


class CaseMessageView(_Staff):
    perms_map = {"POST": MANAGE}

    def post(self, request, pk):
        c = get_object_or_404(_cases_qs(), pk=pk)
        if c.kind != CaseKind.WINBACK:
            return _send(request, c.user, c)
        from .retention import send_winback

        d = request.data or {}
        tpl = MessageTemplate.objects.filter(pk=d["template"]).first() if d.get("template") else None
        try:
            send_winback(c, request.user, template=tpl if not d.get("body_fa") else None, body_fa=d.get("body_fa") or "",
                         body_en=d.get("body_en") or "", via_site=_truthy(d.get("via_site", True)),
                         via_bot=_truthy(d.get("via_bot", True)), via_email=_truthy(d.get("via_email", False)))
        except Exception as exc:  # noqa: BLE001
            return _err(exc)
        return Response({"ok": True, "message": "Message sent", "message_fa": "پیام ارسال شد"})


class CaseDiscountView(_Staff):
    perms_map = {"POST": MANAGE}

    def post(self, request, pk):
        from .retention import RetentionError, issue_code

        c = get_object_or_404(_cases_qs(), pk=pk)
        d = request.data or {}
        try:
            dc = issue_code(c, request.user, percent=d.get("percent"), days=d.get("days"))
        except RetentionError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=exc.status)
        return Response({"code": dc.code, "percent": dc.percent, "expires_at": dc.expires_at,
                         "message": f"Discount code {dc.code} ({dc.percent}%) created", "message_fa": f"کد تخفیف {dc.code} ({dc.percent}٪) ساخته شد"},
                        status=201)


class CaseTicketView(_Staff):
    perms_map = {"POST": MANAGE}

    def post(self, request, pk):
        c = get_object_or_404(_cases_qs(), pk=pk)
        d = request.data or {}
        if c.ticket_id:
            return Response({"detail": "this case already has a ticket", "code": "has_ticket"}, status=409)
        try:
            S.open_ticket_for(c, request.user, topic_id=d.get("topic") or S.connection_topic_id(), subject=d.get("subject"),
                              body=d.get("body"))
        except Exception as exc:  # noqa: BLE001
            return _err(exc)
        return Response(case_row(_cases_qs().get(pk=pk)), status=201)


# --- leads ------------------------------------------------------------------------------
class LeadsView(_Staff):
    perms_map = {"GET": VIEW}

    def get(self, request):
        p = request.query_params
        qs = (User.objects.filter(deleted_at__isnull=True)
              .exclude(orders__status__in=S.BOUGHT)
              .annotate(last_ticket=Max("tickets__last_activity_at"),
                        pre_tickets=Count("tickets", filter=Q(tickets__topic__requires_active_service=False), distinct=True),
                        open_cases=Count("crm_cases", filter=Q(crm_cases__status=CaseStatus.OPEN), distinct=True)))
        q = (p.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(username__icontains=q) | Q(phone__icontains=q) | Q(name__icontains=q) | Q(email__icontains=q))
        if p.get("with_tickets") == "1":
            qs = qs.filter(pre_tickets__gt=0)
        try:
            off = max(0, int(p.get("offset", 0)))
        except ValueError:
            off = 0
        total = qs.count()
        rows = []
        for u in qs.order_by("-created_at")[off:off + PAGE]:
            last = max([x for x in (u.created_at, u.last_login, u.last_ticket) if x])
            prof = getattr(u, "crm", None) if hasattr(u, "crm") else None
            rows.append({"id": u.id, "username": u.username, "name": u.name, "phone": u.phone, "source": u.source,
                         "created_at": u.created_at, "last_activity": last, "pre_tickets": u.pre_tickets,
                         "open_cases": u.open_cases, "stage": prof.effective_stage if prof else Stage.LEAD,
                         "owner": _staff_row(prof.owner) if prof else None})
        return Response({"count": total, "next": off + PAGE if off + PAGE < total else None, "results": rows})


# --- reports ----------------------------------------------------------------------------
class ReportsView(_Staff):
    perms_map = {"GET": VIEW}

    def get(self, request):
        try:
            days = int(request.query_params.get("days", 30))
        except ValueError:
            days = 30
        since = timezone.now() - timedelta(days=days) if days > 0 else None
        opened = FollowUpCase.objects.all()
        closed = FollowUpCase.objects.filter(status=CaseStatus.CLOSED)
        if since:
            opened, closed = opened.filter(opened_at__gte=since), closed.filter(closed_at__gte=since)
        hours = [(c.closed_at - c.opened_at).total_seconds() / 3600 for c in closed.only("opened_at", "closed_at") if c.closed_at]
        reasons = {r.id: r for r in CaseReason.objects.all()}
        by_reason = [{"reason": ({"id": rid, "name_fa": reasons[rid].name_fa, "name_en": reasons[rid].name_en} if rid in reasons else None),
                      "count": n} for rid, n in opened.values_list("reason").annotate(n=Count("id")).values_list("reason", "n")]
        from .models import CustomerProfile

        stages = {}
        for p in CustomerProfile.objects.only("stage", "stage_override"):
            stages[p.effective_stage] = stages.get(p.effective_stage, 0) + 1
        return Response({
            "days": days,
            "open_now": dict(FollowUpCase.objects.filter(status=CaseStatus.OPEN).values_list("kind").annotate(n=Count("id")).values_list("kind", "n")),
            "opened": opened.count(), "opened_by_kind": dict(opened.values_list("kind").annotate(n=Count("id")).values_list("kind", "n")),
            "by_reason": sorted(by_reason, key=lambda x: -x["count"]),
            "outcomes": dict(closed.values_list("outcome").annotate(n=Count("id")).values_list("outcome", "n")),
            "closed_by_system": closed.filter(closed_by_system=True).count(),
            "resolve_hours": {"count": len(hours), "avg": round(sum(hours) / len(hours), 1) if hours else None,
                              "median": round(statistics.median(hours), 1) if hours else None},
            "stages": stages,
        })


# --- settings, reasons, templates, tags ------------------------------------------------------
class SettingsView(_Staff):
    perms_map = {"GET": VIEW, "PATCH": MANAGE}

    def get(self, request):
        return Response({"settings": S.all_settings(), "limits": {k: [lo, hi] for k, _d, lo, hi in S.INT_SETTINGS}})

    def patch(self, request):
        d = request.data or {}
        changed = {}
        for k, _d, lo, hi in S.INT_SETTINGS:
            if k in d:
                try:
                    v = max(lo, min(hi, int(d[k])))
                except (TypeError, ValueError):
                    return Response({"detail": f"{k} must be a number", "code": "invalid"}, status=400)
                set_setting(k, v, ValueType.INT)
                changed[k] = v
        for k, _d in S.BOOL_SETTINGS:
            if k in d:
                set_setting(k, _truthy(d[k]), ValueType.BOOL)
                changed[k] = _truthy(d[k])
        for k, _d in S.STR_SETTINGS:
            if k in d:
                v = str(d[k] or "").strip()[:300]
                if v and not v.startswith(("https://", "http://")):
                    return Response({"detail": f"{k} must be a http(s) URL", "code": "invalid"}, status=400)
                set_setting(k, v, ValueType.STR)
                changed[k] = v
        if changed:
            write_audit(action="crm.settings", staff=request.user, detail=changed)
        return Response({"settings": S.all_settings()})


def _crud(model, fields, row):
    class ListView(_Staff):
        perms_map = {"GET": VIEW, "POST": MANAGE}

        def get(self, request):
            qs = model.objects.all()
            cat = request.query_params.get("category")
            if cat and "category" in fields:
                qs = qs.filter(category=cat)
            return Response([row(x) for x in qs])

        def post(self, request):
            data = {f: request.data.get(f) for f in fields if f in request.data}
            for f, kind in fields.items():
                if kind == "bool" and f in data:
                    data[f] = _truthy(data[f])
                if kind == "int" and f in data:
                    data[f] = int(data[f] or 0)
            req = [f for f, kind in fields.items() if kind == "req"]
            if any(not str(data.get(f) or "").strip() for f in req):
                return Response({"detail": f"required: {', '.join(req)}", "code": "invalid"}, status=400)
            from django.db import IntegrityError, transaction

            try:
                with transaction.atomic():
                    obj = model.objects.create(**data)
            except IntegrityError:
                return Response({"detail": "already exists", "code": "exists"}, status=409)
            write_audit(action=f"crm.{model._meta.model_name}_created", staff=request.user, target=obj)
            return Response(row(obj), status=201)

    class DetailView(_Staff):
        perms_map = {"PATCH": MANAGE, "DELETE": MANAGE}

        def patch(self, request, pk):
            obj = get_object_or_404(model, pk=pk)
            for f, kind in fields.items():
                if f in request.data:
                    v = request.data[f]
                    v = _truthy(v) if kind == "bool" else int(v or 0) if kind == "int" else str(v or "")
                    if kind == "req" and not v.strip():
                        return Response({"detail": f"{f} is required", "code": "invalid"}, status=400)
                    setattr(obj, f, v)
            from django.db import IntegrityError, transaction

            try:
                with transaction.atomic():
                    obj.save()
            except IntegrityError:
                return Response({"detail": "already exists", "code": "exists"}, status=409)
            write_audit(action=f"crm.{model._meta.model_name}_updated", staff=request.user, target=obj)
            return Response(row(obj))

        def delete(self, request, pk):
            obj = get_object_or_404(model, pk=pk)
            if model is CaseReason and obj.cases.exists():
                return Response({"detail": "this reason is used by cases — deactivate it instead", "code": "in_use"}, status=409)
            write_audit(action=f"crm.{model._meta.model_name}_deleted", staff=request.user, target=obj)
            obj.delete()
            return Response(status=204)

    return ListView, DetailView


ReasonsView, ReasonDetailView = _crud(CaseReason, {"name_fa": "req", "name_en": "req", "is_active": "bool", "sort_order": "int",
                                                  "category": "str"},
                                      lambda r: {"id": r.id, "category": r.category, "name_fa": r.name_fa, "name_en": r.name_en, "is_active": r.is_active,
                                                 "sort_order": r.sort_order, "used": r.cases.count()})
TemplatesView, TemplateDetailView = _crud(MessageTemplate, {"title": "req", "body_fa": "req", "body_en": "str", "is_active": "bool",
                                                            "sort_order": "int", "category": "str"},
                                          lambda t: {"id": t.id, "category": t.category, "title": t.title, "body_fa": t.body_fa, "body_en": t.body_en,
                                                     "is_active": t.is_active, "sort_order": t.sort_order})
TagsView, TagDetailView = _crud(Tag, {"name": "req", "color": "str"}, lambda t: {"id": t.id, "name": t.name, "color": t.color})



class StaffListView(_Staff):
    perms_map = {"GET": VIEW}

    def get(self, request):
        return Response([_staff_row(s) for s in Staff.objects.filter(is_active=True).select_related("role")
                         if s.is_superadmin or s.has_perm("crm.view")])



# --- retention (phase 4) -------------------------------------------------------------
from .models import WarningRule  # noqa: E402

WarningRulesView, WarningRuleDetailView = _crud(
    WarningRule, {"kind": "req", "threshold": "int", "is_active": "bool", "title_fa": "req", "title_en": "str", "body_fa": "req",
                  "body_en": "str"},
    lambda w: {"id": w.id, "kind": w.kind, "threshold": w.threshold, "is_active": w.is_active, "title_fa": w.title_fa,
               "title_en": w.title_en, "body_fa": w.body_fa, "body_en": w.body_en, "sent": w.sent.count()})


class RetentionSettingsView(_Staff):
    perms_map = {"GET": VIEW, "PATCH": MANAGE}

    def get(self, request):
        from . import retention as R

        return Response({"settings": R.all_settings()})

    def patch(self, request):
        from . import retention as R

        d = request.data or {}
        changed = {}
        for k, _d, lo, hi in R.INT_SETTINGS:
            if k in d:
                try:
                    v = max(lo, min(hi, int(d[k] or 0)))
                except (TypeError, ValueError):
                    return Response({"detail": f"{k} must be a number", "code": "invalid"}, status=400)
                set_setting(k, v, ValueType.INT)
                changed[k] = v
        for k, _d in R.BOOL_SETTINGS:
            if k in d:
                set_setting(k, _truthy(d[k]), ValueType.BOOL)
                changed[k] = _truthy(d[k])
        for k, _d in R.STR_SETTINGS:
            if k in d:
                v = str(d[k] or "").strip()
                if v and R._hm(v) is None:
                    return Response({"detail": f"{k} must be HH:MM", "code": "invalid"}, status=400)
                set_setting(k, v, ValueType.STR)
                changed[k] = v
        if changed:
            write_audit(action="crm.retention_settings", staff=request.user, detail=changed)
        return Response({"settings": R.all_settings()})


class RetentionReportView(_Staff):
    perms_map = {"GET": VIEW}

    def get(self, request):
        from .retention import report

        try:
            days = int(request.query_params.get("days", 30))
        except ValueError:
            days = 30
        return Response(report(days))



# --- analytics (phase 5) ------------------------------------------------------------------
ANALYTICS = ["accounting.view", "crm.view"]


class AnalyticsView(_Staff):
    """GET analytics/<what>/ — overview | financial | retention | tickets (period: ?preset= or ?from=&to=)
    · ?export=csv|xlsx on financial (with the retention tables) → a file."""

    def get_permissions(self):
        self.perms_map = {"GET": ["crm.view", "tickets.view"] if self.kwargs.get("what") == "tickets" else ANALYTICS}
        return super().get_permissions()

    def get(self, request, what):
        from django.http import HttpResponse

        from . import analytics as A

        start, end, preset = A.parse_period(request.query_params)
        if what == "overview":
            return Response(A.overview())
        if what == "financial":
            fin = A.financial(start, end)
            exp = request.query_params.get("export")
            if exp in ("csv", "xlsx"):
                lang = request.query_params.get("lang", "fa")
                rows = A.export_rows(fin, A.retention(start, end), lang)
                name = f"crm-financial-{A._rng(start, end)['from'].replace('/', '')}-{A._rng(start, end)['to'].replace('/', '')}"
                if exp == "csv":
                    resp = HttpResponse(A.to_csv(rows), content_type="text/csv; charset=utf-8")
                    resp["Content-Disposition"] = f'attachment; filename="{name}.csv"'
                    return resp
                from apps.common.xlsx import build

                resp = HttpResponse(build(rows, sheet="CRM", rtl=lang != "en"),
                                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                resp["Content-Disposition"] = f'attachment; filename="{name}.xlsx"'
                return resp
            return Response({"range": A._rng(start, end), "preset": preset, **fin})
        if what == "retention":
            return Response({"range": A._rng(start, end), "preset": preset, **A.retention(start, end)})
        if what == "tickets":
            return Response({"range": A._rng(start, end), "preset": preset, **A.tickets(start, end)})
        return Response({"detail": "unknown report"}, status=404)
