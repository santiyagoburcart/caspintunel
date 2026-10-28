"""CRM accounting & analytics (Phase 5) — read-only, from existing data.

Revenue = approved payments by `confirmed_at` (exactly as the Accounting page).
Months are Jalali months in Tehran time.

Definitions (shown on the page too):
  AOV       revenue / approved payments in the period
  ARPU      revenue / paying customers in the period
  new vs returning revenue: a payment is "new" when it is that customer's first approved payment ever
  coverage  every paid / completed new / renew order covers [created, created + plan days] (30 days when
            the plan has no duration); a customer is "active" in a month when a coverage overlaps it
  churn (month M)    customers active in M-1 and not in M / active in M-1
  renewal (month M)  orders whose coverage ends in M that the customer followed with another paid order
                     by the end + `crm_renewal_grace_days` (14) / those orders
  lifetime  first purchase → end of the last coverage (or today), averaged over customers
Tickets: handled = distinct tickets a staff member replied to; first response = ticket created → first
staff reply (credited to that replier); resolution = created → closed (credited to the assignee, else the
closer); reopened = reopen events on tickets assigned to them.
"""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from statistics import mean
from zoneinfo import ZoneInfo

import jdatetime
from django.db.models import Count, Min, Sum
from django.utils import timezone

TZ = ZoneInfo("Asia/Tehran")
D0 = Decimal(0)
BOUGHT = ("paid", "completed")
RENEWAL_GRACE_DAYS = 14


# --- dates ------------------------------------------------------------------------------
def local_date(dt) -> date:
    return dt.astimezone(TZ).date()


def jkey(d: date) -> tuple[int, int]:
    j = jdatetime.date.fromgregorian(date=d)
    return j.year, j.month


def jlabel(k) -> str:
    return f"{k[0]}/{k[1]:02d}"


def month_start(k) -> date:
    return jdatetime.date(k[0], k[1], 1).togregorian()


def next_key(k):
    return (k[0] + 1, 1) if k[1] == 12 else (k[0], k[1] + 1)


def prev_key(k):
    return (k[0] - 1, 12) if k[1] == 1 else (k[0], k[1] - 1)


def month_range(k) -> tuple[datetime, datetime]:
    s = datetime.combine(month_start(k), datetime.min.time(), tzinfo=TZ)
    e = datetime.combine(month_start(next_key(k)), datetime.min.time(), tzinfo=TZ)
    return s, e


def months_between(a: date, b: date) -> list:
    out, k, end = [], jkey(a), jkey(b)
    while k <= end:
        out.append(k)
        k = next_key(k)
    return out


def parse_period(params) -> tuple[datetime, datetime, str]:
    """?preset=this_month|last_month|3m|6m|12m|all or ?from=&to= (Jalali YYYY/MM/DD or ISO)."""
    now = timezone.now()
    today = local_date(now)
    preset = params.get("preset") or ("custom" if params.get("from") or params.get("to") else "this_month")
    if preset == "custom":
        def p(v, end=False):
            if not v:
                return None
            v = v.strip()
            try:
                if "/" in v:
                    y, m, d = (int(x) for x in v.split("/"))
                    g = jdatetime.date(y, m, d).togregorian()
                else:
                    g = date.fromisoformat(v)
            except (ValueError, TypeError):
                return None
            dt = datetime.combine(g, datetime.min.time(), tzinfo=TZ)
            return dt + timedelta(days=1) if end else dt
        start = p(params.get("from")) or now - timedelta(days=30)
        end = p(params.get("to"), end=True) or now
        return start, end, "custom"
    k = jkey(today)
    if preset == "last_month":
        s, e = month_range(prev_key(k))
        return s, e, preset
    if preset in ("3m", "6m", "12m"):
        n = int(preset[:-1])
        kk = k
        for _ in range(n - 1):
            kk = prev_key(kk)
        return month_range(kk)[0], now, preset
    if preset == "all":
        from apps.payments_sms.models import Payment

        first = Payment.objects.live().filter(status="approved").order_by("confirmed_at").values_list("confirmed_at", flat=True).first()
        return (first or now - timedelta(days=30)), now, preset
    return month_range(k)[0], now, "this_month"


def _rng(start, end) -> dict:
    return {"from": jdatetime.datetime.fromgregorian(datetime=start.astimezone(TZ)).strftime("%Y/%m/%d"),
            "to": jdatetime.datetime.fromgregorian(datetime=(end - timedelta(seconds=1)).astimezone(TZ)).strftime("%Y/%m/%d"),
            "from_iso": start.isoformat(), "to_iso": end.isoformat()}


# --- money ------------------------------------------------------------------------------
def _approved():
    from apps.payments_sms.models import Payment

    # voided (deleted by a Super Admin) payments are left out of every figure
    return Payment.objects.live().filter(status="approved", confirmed_at__isnull=False)


def financial(start, end) -> dict:
    qs = _approved().filter(confirmed_at__gte=start, confirmed_at__lt=end).select_related("order", "order__plan", "bank_card")
    rows = list(qs.values("id", "amount", "confirmed_at", "order__user_id", "order__source", "order__plan_id",
                          "order__plan__name_fa", "order__plan__name_en", "bank_card__card_number", "bank_card__bank_name",
                          "order__discount_amount", "order__type"))
    first_pay = dict(_approved().values("order__user_id").annotate(first=Min("confirmed_at")).values_list("order__user_id", "first"))
    revenue = sum((r["amount"] for r in rows), D0)
    payers = {r["order__user_id"] for r in rows}
    monthly = defaultdict(lambda: {"revenue": D0, "count": 0, "new": D0, "returning": D0})
    by_plan, by_channel, by_card = defaultdict(lambda: [D0, 0, "", ""]), defaultdict(lambda: [D0, 0]), defaultdict(lambda: [D0, 0, ""])
    new_rev = ret_rev = discount = D0
    for r in rows:
        k = jkey(local_date(r["confirmed_at"]))
        is_new = first_pay.get(r["order__user_id"]) == r["confirmed_at"]
        m = monthly[k]
        m["revenue"] += r["amount"]
        m["count"] += 1
        m["new" if is_new else "returning"] += r["amount"]
        if is_new:
            new_rev += r["amount"]
        else:
            ret_rev += r["amount"]
        p = by_plan[r["order__plan_id"]]
        p[0] += r["amount"]
        p[1] += 1
        p[2], p[3] = r["order__plan__name_fa"] or "—", r["order__plan__name_en"] or ""
        c = by_channel[r["order__source"] or "site"]
        c[0] += r["amount"]
        c[1] += 1
        card = r["bank_card__card_number"] or "—"
        b = by_card[card]
        b[0] += r["amount"]
        b[1] += 1
        b[2] = r["bank_card__bank_name"] or ""
        discount += r["order__discount_amount"] or D0
    keys = months_between(local_date(start), local_date(end - timedelta(seconds=1)))
    from .discounts import totals as discount_totals

    disc = discount_totals(start, end)            # v1.26: every discount code, not only win-back
    codes_used = disc["uses"]
    ltv_all = dict(_approved().values("order__user_id").annotate(s=Sum("amount")).values_list("order__user_id", "s"))
    return {
        "revenue": str(revenue), "payments": len(rows), "paying_customers": len(payers),
        "aov": str(round(revenue / len(rows))) if rows else "0",
        "arpu": str(round(revenue / len(payers))) if payers else "0",
        "new_revenue": str(new_rev), "returning_revenue": str(ret_rev),
        "new_customers": sum(1 for u in payers if start <= first_pay.get(u, start - timedelta(days=1)) < end),
        "discount_cost": str(discount), "codes_used": codes_used,
        "discount_codes": [{**r, "discount": str(r["discount"]), "revenue": str(r["revenue"])} for r in disc["by_code"]],
        "avg_ltv": str(round(sum(ltv_all.values(), D0) / len(ltv_all))) if ltv_all else "0", "customers_with_ltv": len(ltv_all),
        "monthly": [{"month": jlabel(k), **{x: (str(v) if isinstance(v, Decimal) else v) for x, v in monthly[k].items()}}
                    if k in monthly else {"month": jlabel(k), "revenue": "0", "count": 0, "new": "0", "returning": "0"} for k in keys],
        "by_plan": sorted(({"plan_id": pid, "name_fa": v[2], "name_en": v[3], "revenue": str(v[0]), "count": v[1]} for pid, v in by_plan.items()),
                          key=lambda x: -Decimal(x["revenue"])),
        "by_channel": sorted(({"channel": ch, "revenue": str(v[0]), "count": v[1]} for ch, v in by_channel.items()), key=lambda x: -Decimal(x["revenue"])),
        "by_card": sorted(({"card": card[-4:] if card != "—" else "—", "bank": v[2], "revenue": str(v[0]), "count": v[1]} for card, v in by_card.items()),
                          key=lambda x: -Decimal(x["revenue"])),
    }


# --- coverage / retention ----------------------------------------------------------------
def coverages() -> dict:
    """user_id → sorted [(start_date, end_date, created_at, order_id)] from paid / completed new + renew orders."""
    from apps.orders.models import Order

    out = defaultdict(list)
    # an order whose payment a Super Admin deleted (voided) is not a purchase for cohorts either
    for o in Order.objects.filter(status__in=BOUGHT, type__in=("new", "renew")).exclude(
            payment__voided_at__isnull=False).select_related("plan").only(
            "id", "user_id", "created_at", "plan__duration_days"):
        days = (o.plan.duration_days if o.plan and o.plan.duration_days else 30)
        s = local_date(o.created_at)
        out[o.user_id].append((s, s + timedelta(days=days), o.created_at, o.id))
    for v in out.values():
        v.sort()
    return out


def _active_in(cov, k) -> bool:
    s, e = month_start(k), month_start(next_key(k))
    return any(a < e and b >= s for a, b, *_ in cov)


def retention(start, end, months_back: int = 12) -> dict:
    cov = coverages()
    today = local_date(timezone.now())
    last = jkey(local_date(end - timedelta(seconds=1)))
    keys = []
    k = last
    for _ in range(months_back):
        keys.append(k)
        k = prev_key(k)
    keys.reverse()
    active = {k: {u for u, c in cov.items() if _active_in(c, k)} for k in [prev_key(keys[0])] + keys}
    churn = []
    for k in keys:
        prev = active[prev_key(k)]
        lost = prev - active[k]
        churn.append({"month": jlabel(k), "active_prev": len(prev), "active": len(active[k]), "churned": len(lost),
                      "rate": round(len(lost) * 100 / len(prev), 1) if prev else None})
    renew = []
    for k in keys:
        s, e = month_start(k), month_start(next_key(k))
        due = renewed = 0
        for u, c in cov.items():
            for i, (a, b, created, _oid) in enumerate(c):
                if s <= b < e and b <= today:
                    due += 1
                    if any(created < c2 <= datetime.combine(b + timedelta(days=RENEWAL_GRACE_DAYS), datetime.max.time(), tzinfo=TZ)
                           for _a, _b, c2, _o in c[i + 1:]):
                        renewed += 1
        renew.append({"month": jlabel(k), "due": due, "renewed": renewed, "rate": round(renewed * 100 / due, 1) if due else None})
    # cohorts: first purchase month → % active k months later
    cohorts = defaultdict(list)
    for u, c in cov.items():
        cohorts[jkey(c[0][0])].append(u)
    cohort_rows = []
    for ck in keys:
        users = cohorts.get(ck, [])
        if not users:
            continue
        cells, kk = [], ck
        while kk <= jkey(today) and len(cells) < 12:
            cells.append(round(sum(1 for u in users if _active_in(cov[u], kk)) * 100 / len(users), 1))
            kk = next_key(kk)
        cohort_rows.append({"cohort": jlabel(ck), "customers": len(users), "pct": cells})
    lifetimes = [(min(max(b for _a, b, *_ in c), today) - c[0][0]).days for c in cov.values()]
    from apps.accounts.models import User

    ltv = list(_approved().values("order__user_id").annotate(s=Sum("amount"), n=Count("id")).order_by("-s")[:20])
    users = {u.id: u for u in User.objects.filter(id__in=[r["order__user_id"] for r in ltv]).select_related("crm")}
    top = []
    for r in ltv:
        u = users.get(r["order__user_id"])
        if u is None:
            continue
        c = cov.get(u.id, [])
        prof = getattr(u, "crm", None) if hasattr(u, "crm") else None
        top.append({"id": u.id, "username": u.username, "name": u.name, "ltv": str(r["s"]), "payments": r["n"],
                    "first": c[0][0].isoformat() if c else None, "stage": prof.effective_stage if prof else None})
    return {"churn": churn, "renewal": renew, "cohorts": cohort_rows,
            "avg_lifetime_days": round(mean(lifetimes)) if lifetimes else None, "customers": len(cov), "top_ltv": top}


# --- tickets -----------------------------------------------------------------------------
def tickets(start, end) -> dict:
    from apps.tickets.models import Ticket, TicketEvent

    replies = TicketEvent.objects.filter(kind="staff_replied", created_at__gte=start, created_at__lt=end, actor_staff__isnull=False)
    per = defaultdict(lambda: {"handled": set(), "first": [], "resolve": [], "reopened": 0, "replies": 0})
    names = {}
    for e in replies.select_related("actor_staff"):
        p = per[e.actor_staff_id]
        p["handled"].add(e.ticket_id)
        p["replies"] += 1
        names[e.actor_staff_id] = e.actor_staff.display_name or e.actor_staff.username
    created = Ticket.objects.filter(created_at__gte=start, created_at__lt=end)
    first_events = {}
    for e in TicketEvent.objects.filter(kind="staff_replied", ticket__in=created).order_by("created_at").select_related("actor_staff"):
        first_events.setdefault(e.ticket_id, e)
    topic_first = defaultdict(list)
    for t in created.select_related("topic"):
        e = first_events.get(t.id)
        if e and e.actor_staff_id:
            mins = (e.created_at - t.created_at).total_seconds() / 60
            per[e.actor_staff_id]["first"].append(mins)
            names.setdefault(e.actor_staff_id, e.actor_staff.display_name or e.actor_staff.username)
            topic_first[t.topic_id].append(mins)
    closed = Ticket.objects.filter(closed_at__gte=start, closed_at__lt=end).select_related("assigned_to", "closed_by")
    for t in closed:
        who = t.assigned_to or t.closed_by
        if who is None:
            continue
        per[who.id]["resolve"].append((t.closed_at - t.created_at).total_seconds() / 3600)
        names.setdefault(who.id, who.display_name or who.username)
    for e in TicketEvent.objects.filter(kind="reopened", created_at__gte=start, created_at__lt=end).select_related("ticket__assigned_to"):
        a = e.ticket.assigned_to
        if a is not None:
            per[a.id]["reopened"] += 1
            names.setdefault(a.id, a.display_name or a.username)
    staff = [{"id": sid, "name": names.get(sid, f"#{sid}"), "handled": len(p["handled"]), "replies": p["replies"],
              "first_response_min": round(mean(p["first"]), 1) if p["first"] else None,
              "resolution_h": round(mean(p["resolve"]), 1) if p["resolve"] else None,
              "resolved": len(p["resolve"]), "reopened": p["reopened"]} for sid, p in per.items()]
    from apps.tickets.models import TicketTopic

    topics = []
    tcount = dict(created.values_list("topic").annotate(n=Count("id")).values_list("topic", "n"))
    ccount = dict(closed.values_list("topic").annotate(n=Count("id")).values_list("topic", "n"))
    for tp in TicketTopic.objects.all():
        if tcount.get(tp.id) or ccount.get(tp.id):
            fr = topic_first.get(tp.id, [])
            topics.append({"id": tp.id, "name_fa": tp.name_fa, "name_en": tp.name_en, "opened": tcount.get(tp.id, 0),
                           "closed": ccount.get(tp.id, 0), "first_response_min": round(mean(fr), 1) if fr else None})
    allfirst = [m for p in per.values() for m in p["first"]]
    return {"staff": sorted(staff, key=lambda x: -x["handled"]), "topics": sorted(topics, key=lambda x: -x["opened"]),
            "opened": created.count(), "closed": closed.count(),
            "open_now": Ticket.objects.exclude(status="closed").count(),
            "avg_first_response_min": round(mean(allfirst), 1) if allfirst else None,
            "reopened": TicketEvent.objects.filter(kind="reopened", created_at__gte=start, created_at__lt=end).count()}


# --- overview ----------------------------------------------------------------------------
def overview() -> dict:
    from apps.panel.models import Service
    from apps.tickets.models import Ticket

    from .models import CaseKind, CaseStatus, CustomerProfile, FollowUpCase, Outcome

    now = timezone.now()
    k = jkey(local_date(now))
    this_s, _ = month_range(k)
    prev_s, prev_e = month_range(prev_key(k))
    rev = lambda a, b: _approved().filter(confirmed_at__gte=a, confirmed_at__lt=b).aggregate(s=Sum("amount"))["s"] or D0  # noqa: E731
    this_rev = rev(this_s, now)
    # same elapsed part of last month, for a fair comparison
    prev_same = rev(prev_s, min(prev_s + (now - this_s), prev_e))
    stages = defaultdict(int)
    for p in CustomerProfile.objects.only("stage", "stage_override"):
        stages[p.effective_stage] += 1
    month_ago = now - timedelta(days=30)
    wb = FollowUpCase.objects.filter(kind=CaseKind.WINBACK, status=CaseStatus.CLOSED, closed_at__gte=month_ago)
    t = tickets(month_ago, now)
    keys = []
    kk = k
    for _ in range(12):
        keys.append(kk)
        kk = prev_key(kk)
    keys.reverse()
    cov = coverages()
    rev_series, new_series, active_series = [], [], []
    first_pay = defaultdict(lambda: None)
    for u, c in cov.items():
        first_pay[u] = c[0][0]
    for key in keys:
        s, e = month_range(key)
        rev_series.append({"month": jlabel(key), "value": str(rev(s, min(e, now)))})
        new_series.append({"month": jlabel(key), "value": sum(1 for d in first_pay.values() if d and jkey(d) == key)})
        active_series.append({"month": jlabel(key), "value": sum(1 for c in cov.values() if _active_in(c, key))})
    weeks = []
    for i in range(11, -1, -1):
        ws, we = now - timedelta(days=7 * (i + 1)), now - timedelta(days=7 * i)
        weeks.append({"week": local_date(ws).isoformat(), "value": Ticket.objects.filter(created_at__gte=ws, created_at__lt=we).count()})
    return {
        "month": jlabel(k),
        "revenue_month": str(this_rev), "revenue_prev_same": str(prev_same),
        "revenue_change": round(float((this_rev - prev_same) * 100 / prev_same), 1) if prev_same else None,
        "active_customers": Service.objects.filter(status__in=("active", "on_hold"), user__deleted_at__isnull=True).values("user").distinct().count(),
        "at_risk": stages.get("at_risk", 0), "expired": stages.get("expired", 0), "churned": stages.get("churned", 0),
        "winback_rate": round(wb.filter(outcome=Outcome.WON_BACK).count() * 100 / wb.count(), 1) if wb.count() else None,
        "open_tickets": t["open_now"], "avg_first_response_min": t["avg_first_response_min"],
        "open_cases": FollowUpCase.objects.filter(status=CaseStatus.OPEN).count(),
        "trends": {"revenue": rev_series, "new_customers": new_series, "active": active_series, "tickets": weeks},
    }


# --- export ------------------------------------------------------------------------------
def export_rows(fin: dict, ret: dict | None, lang: str) -> list[list]:
    fa = lang != "en"
    rows = [["گزارش مالی مشتریان" if fa else "Customer financial report"], []]
    rows += [["درآمد" if fa else "Revenue", Decimal(fin["revenue"])], ["پرداخت‌ها" if fa else "Payments", fin["payments"]],
             ["مشتریان پرداخت‌کننده" if fa else "Paying customers", fin["paying_customers"]], ["AOV", Decimal(fin["aov"])],
             ["ARPU", Decimal(fin["arpu"])], ["درآمد مشتریان جدید" if fa else "New-customer revenue", Decimal(fin["new_revenue"])],
             ["درآمد مشتریان قبلی" if fa else "Returning revenue", Decimal(fin["returning_revenue"])],
             ["هزینهٔ تخفیف" if fa else "Discount cost", Decimal(fin["discount_cost"])], []]
    rows += [["ماه" if fa else "Month", "درآمد" if fa else "Revenue", "تعداد" if fa else "Count", "جدید" if fa else "New", "قبلی" if fa else "Returning"]]
    rows += [[m["month"], Decimal(m["revenue"]), m["count"], Decimal(m["new"]), Decimal(m["returning"])] for m in fin["monthly"]]
    rows += [[], ["پلن" if fa else "Plan", "درآمد" if fa else "Revenue", "تعداد" if fa else "Count"]]
    rows += [[p["name_fa"] if fa else (p["name_en"] or p["name_fa"]), Decimal(p["revenue"]), p["count"]] for p in fin["by_plan"]]
    rows += [[], ["کانال" if fa else "Channel", "درآمد" if fa else "Revenue", "تعداد" if fa else "Count"]]
    rows += [[c["channel"], Decimal(c["revenue"]), c["count"]] for c in fin["by_channel"]]
    rows += [[], ["کارت" if fa else "Card", "بانک" if fa else "Bank", "درآمد" if fa else "Revenue", "تعداد" if fa else "Count"]]
    rows += [[c["card"], c["bank"], Decimal(c["revenue"]), c["count"]] for c in fin["by_card"]]
    if ret:
        rows += [[], ["ماه" if fa else "Month", "ریزش %" if fa else "Churn %", "تمدید %" if fa else "Renewal %"]]
        for c, r in zip(ret["churn"], ret["renewal"]):
            rows.append([c["month"], c["rate"] if c["rate"] is not None else "", r["rate"] if r["rate"] is not None else ""])
        rows += [[], ["مشتری" if fa else "Customer", "LTV", "پرداخت‌ها" if fa else "Payments"]]
        rows += [[t["username"], Decimal(t["ltv"]), t["payments"]] for t in ret["top_ltv"]]
    return rows


def to_csv(rows) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    for r in rows:
        w.writerow(r)
    return ("﻿" + buf.getvalue()).encode("utf-8")
