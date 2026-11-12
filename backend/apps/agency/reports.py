"""Accounting reports over the agency ledger (read-only; PAMP numbers untouched).

Definitions (voided entries are excluded everywhere):
  sales       = quota + manual charges + adjustments («کاهش بدهی» −, «افزایش بدهی» +) in the period they are recorded
                («فروش», v1.57 — the one sales / income figure; gross charges are never shown)
  adjust_*    = «اصلاحیه‌ها», information only: adjust_count, adjust_down («کاهش بدهی» T), adjust_up («افزایش بدهی» T);
                `adjustments` = signed sum. `charges` / `net_sales` stay in the API for older pages.
  payments    = payments received
  net         = charges + adjustments − payments   (what the period added to the resellers' balances)
  GB        = GB on charge entries (the volume granted)
Periods and months are Jalali; dates in the API are ISO (Gregorian)."""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

import jdatetime

from .models import LedgerEntry

PAY = LedgerEntry.KIND_PAYMENT
D0 = Decimal(0)


def _live():
    return LedgerEntry.objects.filter(voided=False)


def _sum(entries) -> dict:
    t = {"charges": D0, "adjustments": D0, "adjust_count": 0, "adjust_down": D0, "adjust_up": D0, "payments": D0, "gb": D0,
         "payments_count": 0, "resellers": set()}
    for e in entries:
        if e.kind == PAY:
            t["payments"] += e.amount
            t["payments_count"] += 1
        elif e.kind == LedgerEntry.KIND_ADJUST:
            t["adjustments"] += e.amount
            t["adjust_count"] += 1
            t["adjust_down" if e.amount < 0 else "adjust_up"] += abs(e.amount)
        else:
            t["charges"] += e.amount
            t["gb"] += e.gb or D0
            t["resellers"].add(e.admin_username)
    t["sales"] = t["net_sales"] = t["charges"] + t["adjustments"]
    t["net"] = t["charges"] + t["adjustments"] - t["payments"]
    return t


def _adj(t) -> dict:
    """«اصلاحیه‌ها» as information (v1.57): count + T of debt decreases / increases + the signed sum."""
    return {"adjustments": _money(t["adjustments"]), "adjust_count": t["adjust_count"], "adjust_down": _money(t["adjust_down"]),
            "adjust_up": _money(t["adjust_up"])}


def _money(x) -> int:
    return int(x or 0)


def _gb(x) -> float:
    return float(round(Decimal(x or 0), 2))


def jmonth_bounds(jy: int, jm: int) -> tuple[date, date]:
    start = jdatetime.date(jy, jm, 1).togregorian()
    nxt = jdatetime.date(jy + (jm == 12), 1 if jm == 12 else jm + 1, 1).togregorian()
    return start, nxt - timedelta(days=1)


def jkey(d: date) -> tuple[int, int]:
    j = jdatetime.date.fromgregorian(date=d)
    return j.year, j.month


def overview(frm: date, to: date) -> dict:
    entries = list(_live().filter(date__gte=frm, date__lte=to).order_by("date", "id"))
    t = _sum(entries)
    # all-time balances: what resellers owe (positive) and hold in credit (negative)
    bal = defaultdict(lambda: D0)
    for e in _live().only("admin_username", "kind", "amount"):
        bal[e.admin_username] += e.signed_amount
    owed = sum((b for b in bal.values() if b > 0), D0)
    credit = sum((-b for b in bal.values() if b < 0), D0)
    # series: per day up to ~2 months, else per Jalali month
    by_month = (to - frm).days > 62
    buckets: dict = {}
    if by_month:
        y, m = jkey(frm)
        while (y, m) <= jkey(to):
            buckets[(y, m)] = {"charges": D0, "payments": D0, "adjustments": D0}
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    else:
        d = frm
        while d <= to:
            buckets[d] = {"charges": D0, "payments": D0, "adjustments": D0}
            d += timedelta(days=1)
    for e in entries:
        k = jkey(e.date) if by_month else e.date
        if k in buckets:
            buckets[k]["payments" if e.kind == PAY else "adjustments" if e.kind == LedgerEntry.KIND_ADJUST else "charges"] += e.amount
    # v1.57: the chart shows «فروش» (charges + adjustments of that day / month), never the gross charges
    series = [{"key": (f"{k[0]}/{k[1]:02d}" if by_month else k.isoformat()), "sales": _money(v["charges"] + v["adjustments"]),
               "charges": _money(v["charges"] + v["adjustments"]), "payments": _money(v["payments"])} for k, v in buckets.items()]
    recent = [e for e in reversed(entries) if e.kind == PAY][:50]
    return {
        "from": frm, "to": to, "bucket": "month" if by_month else "day",
        "kpis": {**_adj(t), "charges": _money(t["charges"]), "sales": _money(t["sales"]), "net_sales": _money(t["net_sales"]),
                 "payments": _money(t["payments"]),
                 "net": _money(t["net"]),
                 "gb": _gb(t["gb"]), "payments_count": t["payments_count"],
                 "outstanding": _money(owed), "credit": _money(credit), "resellers_owing": sum(1 for b in bal.values() if b > 0)},
        "series": series,
        "recent_payments": [{"id": e.id, "date": e.date, "username": e.admin_username, "amount": _money(e.amount),
                             "method": e.method, "note": e.note} for e in recent],
    }


def monthly() -> list[dict]:
    """One row per Jalali month that has ledger entries, newest first."""
    groups = defaultdict(list)
    for e in _live().order_by("date", "id"):
        groups[jkey(e.date)].append(e)
    rows = []
    for (jy, jm), es in sorted(groups.items(), reverse=True):
        t = _sum(es)
        rows.append({"year": jy, "month": jm, "gb": _gb(t["gb"]), "charges": _money(t["charges"]), **_adj(t),
                     "sales": _money(t["sales"]), "net_sales": _money(t["net_sales"]), "payments": _money(t["payments"]),
                     "net": _money(t["net"]),
                     "resellers_charged": len(t["resellers"]), "payments_count": t["payments_count"]})
    return rows


def month_breakdown(jy: int, jm: int) -> dict:
    start, end = jmonth_bounds(jy, jm)
    per = defaultdict(list)
    closing = defaultdict(lambda: D0)
    for e in _live().filter(date__lte=end).order_by("date", "id"):
        closing[e.admin_username] += e.signed_amount
        if e.date >= start:
            per[e.admin_username].append(e)
    rows = []
    for u, es in per.items():
        t = _sum(es)
        rows.append({"username": u, "gb": _gb(t["gb"]), "charges": _money(t["charges"]), **_adj(t), "sales": _money(t["sales"]),
                     "net_sales": _money(t["net_sales"]), "payments": _money(t["payments"]), "net": _money(t["net"]), "balance_end": _money(closing[u])})
    rows.sort(key=lambda r: (-r["sales"], r["username"]))
    tot = _sum([e for es in per.values() for e in es])
    return {"year": jy, "month": jm, "start": start, "end": end, "rows": rows,
            "totals": {"gb": _gb(tot["gb"]), "charges": _money(tot["charges"]), **_adj(tot), "sales": _money(tot["sales"]),
                       "net_sales": _money(tot["net_sales"]),
                       "payments": _money(tot["payments"]), "net": _money(tot["net"])}}


# ---- exports ------------------------------------------------------------------
MONTHLY_HEAD = {"fa": ["ماه", "گیگ واگذارشده", "فروش (تومان)", "پرداخت (تومان)", "خالص (تومان)", "نماینده‌های شارژشده", "تعداد پرداخت"],
                "en": ["Month", "GB granted", "Sales (Toman)", "Payments (Toman)", "Net (Toman)", "Resellers charged", "Payments"]}
BREAK_HEAD = {"fa": ["نماینده", "گیگ واگذارشده", "فروش (تومان)", "پرداخت (تومان)", "خالص (تومان)", "مانده پایان ماه (تومان)"],
              "en": ["Reseller", "GB granted", "Sales (Toman)", "Payments (Toman)", "Net (Toman)", "Balance at month end (Toman)"]}
ADJ_INFO = {"fa": "اصلاحیه‌ها (فقط اطلاع؛ در «فروش» حساب شده) — تعداد {n} · کاهش بدهی {d} · افزایش بدهی {u} تومان",
            "en": "Adjustments (information only, already in «Sales») — count {n} · debt decreases {d} · debt increases {u} T"}


def _adj_line(t: dict, lang: str) -> list:
    return [ADJ_INFO.get(lang, ADJ_INFO["en"]).format(n=t["adjust_count"], d=t["adjust_down"], u=t["adjust_up"])]


def monthly_rows(lang: str) -> list[list]:
    return [MONTHLY_HEAD.get(lang, MONTHLY_HEAD["en"])] + [
        [f"{r['year']}/{r['month']:02d}", r["gb"], r["sales"], r["payments"], r["net"], r["resellers_charged"], r["payments_count"]]
        for r in monthly()]


def breakdown_rows(jy: int, jm: int, lang: str) -> list[list]:
    b = month_breakdown(jy, jm)
    out = [BREAK_HEAD.get(lang, BREAK_HEAD["en"])] + [
        [r["username"], r["gb"], r["sales"], r["payments"], r["net"], r["balance_end"]]
        for r in b["rows"]]
    t = b["totals"]
    out.append(["جمع" if lang == "fa" else "Total", t["gb"], t["sales"], t["payments"], t["net"], ""])
    out.append([])
    out.append(_adj_line(t, lang))
    return out


def to_csv(rows: list[list]) -> str:
    buf = io.StringIO()
    buf.write("﻿")                       # BOM: Excel opens UTF-8 (Persian) correctly
    csv.writer(buf).writerows(rows)
    return buf.getvalue()


def parse_day(v):
    """ISO (2026-10-21) or Jalali (1405/07/29) → date; None when missing / invalid."""
    if not v:
        return None
    v = str(v).strip()
    try:
        if "/" in v:
            y, m, d = (int(x) for x in v.split("/"))
            return jdatetime.date(y, m, d).togregorian() if y < 1700 else date(y, m, d)
        return date.fromisoformat(v)
    except (ValueError, TypeError):
        return None


def export_response(rows: list[list], fmt: str, name: str, lang: str):
    """CSV (UTF-8 + BOM) or .xlsx download of report rows (rows[0] = header)."""
    from django.http import HttpResponse

    from apps.common import xlsx

    if fmt == "xlsx":
        resp = HttpResponse(xlsx.build(rows, sheet=name[:31], rtl=lang == "fa", widths=[16] + [18] * (max(len(r) for r in rows) - 1)),
                            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        resp["Content-Disposition"] = f'attachment; filename="{name}.xlsx"'
    else:
        resp = HttpResponse(to_csv(rows), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{name}.csv"'
    resp["Cache-Control"] = "private, no-store"
    return resp
