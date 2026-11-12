"""v1.58 Agency → «حسابداری»: ONE table of every agency admin for a period + the summary strip (read-only).

Per admin: group · «فروش» in the period (charges + adjustments — v1.57) · paid in the period · debt (all-time balance) · last
payment · open invoices (unpaid / under review: count + what is still owed on them). The strip: «فروش», «پرداخت‌شده» (period),
«جمع بدهی» (sum of what admins owe now), «تعداد بدهکارها», «اصلاحیه‌ها» (period, information only).
Tabs: `debtors` (owes, or has an open invoice) · `all`. Filters: group, search; sort by any column; pages.
Periods are Tehran / Jalali (`history.bounds`: month · prev · d7 · custom). Voided ledger entries count nowhere.
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Max, Sum

from apps.common.jalali import jalali_day

from . import history, ledger
from .models import AdminGroup, AdminPrice, AgencyInvoice, LedgerEntry, PanelAdmin

D0 = Decimal(0)
SORTS = ("username", "group", "sales", "paid", "debt", "last_payment", "open_invoices")
TABS = ("debtors", "all")


def _groups():
    from .managers import group_title

    groups = list(AdminGroup.objects.order_by("owner_username"))
    of = {}
    for g in groups:
        for n in g.get_all_usernames():
            of.setdefault(n, g)
    return groups, of, group_title


def rows(frm, to, names=None) -> list[dict]:
    """Every admin (or `names`) with its period numbers and current debt — unfiltered, unsorted."""
    priced = set(AdminPrice.objects.values_list("admin_username", flat=True).distinct())
    if names is None:
        names = (set(PanelAdmin.all_objects.values_list("username", flat=True))
                 | set(LedgerEntry.objects.values_list("admin_username", flat=True).distinct()) | priced)
    names = set(names)
    bal = ledger.balances()
    active = set(PanelAdmin.objects.values_list("username", flat=True))
    archived = set(PanelAdmin.all_objects.filter(archived_at__isnull=False).values_list("username", flat=True))
    _, group_of, title = _groups()
    per = {}
    for e in LedgerEntry.objects.filter(voided=False, date__gte=frm, date__lte=to, admin_username__in=names).only(
            "admin_username", "kind", "amount"):
        t = per.setdefault(e.admin_username, {"sales": D0, "paid": D0, "adjust_count": 0, "adjust_down": D0, "adjust_up": D0})
        if e.kind == LedgerEntry.KIND_PAYMENT:
            t["paid"] += e.amount
        else:
            t["sales"] += e.amount                      # charges + adjustments («فروش», v1.57)
            if e.kind == LedgerEntry.KIND_ADJUST:
                t["adjust_count"] += 1
                t["adjust_down" if e.amount < 0 else "adjust_up"] += abs(e.amount)
    last_pay = dict(LedgerEntry.objects.filter(voided=False, kind=LedgerEntry.KIND_PAYMENT, admin_username__in=names)
                    .values("admin_username").annotate(d=Max("date")).values_list("admin_username", "d"))
    inv = {r["admin_username"]: r for r in AgencyInvoice.objects.filter(
        admin_username__in=names, status__in=(AgencyInvoice.UNPAID, AgencyInvoice.PENDING))
        .values("admin_username").annotate(n=Count("id"), amount=Sum("amount"), paid=Sum("paid_amount"))}
    out = []
    for n in names:
        if n not in bal and n not in active and n not in priced and n not in per:
            continue                                    # an archived admin with nothing on the ledger
        t = per.get(n, {})
        i = inv.get(n) or {}
        g = group_of.get(n)
        out.append({"username": n, "group": {"id": g.id, "name": title(g)} if g else None, "sales": t.get("sales", D0),
                    "paid": t.get("paid", D0), "debt": bal.get(n, D0) or D0, "last_payment": last_pay.get(n),
                    "open_invoices": i.get("n", 0), "open_amount": (i.get("amount") or D0) - (i.get("paid") or D0),
                    "adjust_count": t.get("adjust_count", 0), "adjust_down": t.get("adjust_down", D0), "adjust_up": t.get("adjust_up", D0),
                    "on_panel": n in active, "archived": n in archived})
    return out


def summary(rs: list[dict]) -> dict:
    return {"sales": sum((r["sales"] for r in rs), D0), "paid": sum((r["paid"] for r in rs), D0),
            "debt": sum((r["debt"] for r in rs if r["debt"] > 0), D0), "debtors": sum(1 for r in rs if r["debt"] > 0),
            "credit": sum((-r["debt"] for r in rs if r["debt"] < 0), D0),
            "adjust_count": sum(r["adjust_count"] for r in rs), "adjust_down": sum((r["adjust_down"] for r in rs), D0),
            "adjust_up": sum((r["adjust_up"] for r in rs), D0)}


def _key(sort: str):
    if sort == "group":
        return lambda r: ((r["group"] or {}).get("name") or "~").lower()
    if sort == "username":
        return lambda r: r["username"].lower()
    if sort == "last_payment":
        return lambda r: r["last_payment"].toordinal() if r["last_payment"] else 0
    return lambda r: r[sort]


def table(*, period: str = "month", frm=None, to=None, tab: str = "debtors", q: str = "", group=None, sort: str = "debt",
          desc: bool = True, page: int = 1, size: int = 25) -> dict:
    a, b = history.bounds(period if period in history.PERIODS else "month", frm, to)
    rs = rows(a, b)
    if group not in (None, ""):
        rs = [r for r in rs if r["group"] and str(r["group"]["id"]) == str(group)]
    strip = summary(rs)                                 # the strip follows the group filter, not the tab / search
    if tab != "all":
        rs = [r for r in rs if r["debt"] > 0 or r["open_invoices"]]
    term = (q or "").strip().lower()
    if term:
        rs = [r for r in rs if term in r["username"].lower() or term in ((r["group"] or {}).get("name") or "").lower()]
    sort = sort if sort in SORTS else "debt"
    rs.sort(key=lambda r: r["username"].lower())        # stable tie-break by name
    rs.sort(key=_key(sort), reverse=desc)
    size = max(5, min(200, int(size or 25)))
    pages = max(1, -(-len(rs) // size))
    page = max(1, min(pages, int(page or 1)))
    shown = rs[(page - 1) * size: page * size]
    groups, _, title = _groups()
    return {"period": period, "from": a, "to": b, "from_jalali": jalali_day(a), "to_jalali": jalali_day(b), "summary": strip,
            "results": shown, "count": len(rs), "page": page, "pages": pages, "page_size": size, "tab": tab if tab in TABS else "debtors",
            "sort": sort, "desc": desc, "groups": [{"id": g.id, "name": title(g)} for g in groups]}
