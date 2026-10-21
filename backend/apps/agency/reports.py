"""Accounting reports over the agency ledger (read-only; PAMP numbers untouched).

Definitions (voided entries are excluded everywhere):
  charges   = quota charges + manual charges + adjustments (adjustments are signed)
  payments  = payments received
  net       = charges − payments   (what the period added to the resellers' balances)
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
    t = {"charges": D0, "payments": D0, "gb": D0, "payments_count": 0, "resellers": set()}
    for e in entries:
        if e.kind == PAY:
            t["payments"] += e.amount
            t["payments_count"] += 1
        else:
            t["charges"] += e.amount
            t["gb"] += e.gb or D0
            t["resellers"].add(e.admin_username)
    t["net"] = t["charges"] - t["payments"]
    return t


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
            buckets[(y, m)] = {"charges": D0, "payments": D0}
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    else:
        d = frm
        while d <= to:
            buckets[d] = {"charges": D0, "payments": D0}
            d += timedelta(days=1)
    for e in entries:
        k = jkey(e.date) if by_month else e.date
        if k in buckets:
            buckets[k]["payments" if e.kind == PAY else "charges"] += e.amount
    series = [{"key": (f"{k[0]}/{k[1]:02d}" if by_month else k.isoformat()), "charges": _money(v["charges"]),
               "payments": _money(v["payments"])} for k, v in buckets.items()]
    recent = [e for e in reversed(entries) if e.kind == PAY][:50]
    return {
        "from": frm, "to": to, "bucket": "month" if by_month else "day",
        "kpis": {"charges": _money(t["charges"]), "payments": _money(t["payments"]), "net": _money(t["net"]),
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
        rows.append({"year": jy, "month": jm, "gb": _gb(t["gb"]), "charges": _money(t["charges"]),
                     "payments": _money(t["payments"]), "net": _money(t["net"]),
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
        rows.append({"username": u, "gb": _gb(t["gb"]), "charges": _money(t["charges"]), "payments": _money(t["payments"]),
                     "net": _money(t["net"]), "balance_end": _money(closing[u])})
    rows.sort(key=lambda r: (-r["charges"], r["username"]))
    tot = _sum([e for es in per.values() for e in es])
    return {"year": jy, "month": jm, "start": start, "end": end, "rows": rows,
            "totals": {"gb": _gb(tot["gb"]), "charges": _money(tot["charges"]), "payments": _money(tot["payments"]),
                       "net": _money(tot["net"])}}


# ---- exports ------------------------------------------------------------------
MONTHLY_HEAD = {"fa": ["ماه", "گیگ واگذارشده", "شارژ (تومان)", "پرداخت (تومان)", "خالص (تومان)", "نماینده‌های شارژشده", "تعداد پرداخت"],
                "en": ["Month", "GB granted", "Charges (Toman)", "Payments (Toman)", "Net (Toman)", "Resellers charged", "Payments"]}
BREAK_HEAD = {"fa": ["نماینده", "گیگ واگذارشده", "شارژ (تومان)", "پرداخت (تومان)", "خالص (تومان)", "مانده پایان ماه (تومان)"],
              "en": ["Reseller", "GB granted", "Charges (Toman)", "Payments (Toman)", "Net (Toman)", "Balance at month end (Toman)"]}


def monthly_rows(lang: str) -> list[list]:
    return [MONTHLY_HEAD.get(lang, MONTHLY_HEAD["en"])] + [
        [f"{r['year']}/{r['month']:02d}", r["gb"], r["charges"], r["payments"], r["net"], r["resellers_charged"], r["payments_count"]]
        for r in monthly()]


def breakdown_rows(jy: int, jm: int, lang: str) -> list[list]:
    b = month_breakdown(jy, jm)
    out = [BREAK_HEAD.get(lang, BREAK_HEAD["en"])] + [
        [r["username"], r["gb"], r["charges"], r["payments"], r["net"], r["balance_end"]] for r in b["rows"]]
    t = b["totals"]
    out.append(["جمع" if lang == "fa" else "Total", t["gb"], t["charges"], t["payments"], t["net"], ""])
    return out


def to_csv(rows: list[list]) -> str:
    buf = io.StringIO()
    buf.write("﻿")                       # BOM: Excel opens UTF-8 (Persian) correctly
    csv.writer(buf).writerows(rows)
    return buf.getvalue()
