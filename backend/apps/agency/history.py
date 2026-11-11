"""v1.54 «تاریخچه» — an agency admin's (or a group's / all agency's) history, never reset by settlement, payments or
adjustments: everything is summed from the immutable records — the ledger (`LedgerEntry`; a mistake is VOIDED, never
edited), the invoices and the first time the sync saw each user (`AgencyUserSeen`, from v1.54 on).

Per period (last 7 days · current Jalali month · last Jalali month · custom) and per Jalali month (last 12):
  gb          volume sold / charged: GB on quota + manual charges
  charged     T of quota + manual charges            ← «فروش»; adjustments are NOT mixed in (they used to be, so a
  adjustments T of adjustments, signed                 «کاهش بدهی» looked like falling sales — v1.54 fix)
  paid        T of payments received
  invoiced    T of invoices issued in the period (voided ones excluded)
  opening / closing  balance before the first day / after the last day (charges + adjustments − payments)
  new_users   users first seen by the sync in the period (None before v1.54's first sync — no earlier record exists)
Days are Tehran days; voided ledger entries count nowhere.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import jdatetime

from apps.common.jalali import jalali_day, parse_day, tehran_day_end, tehran_day_start, tehran_today

from .models import AgencyInvoice, AgencyUserSeen, LedgerEntry, PanelAdmin

D0 = Decimal(0)
PERIODS = ("d7", "month", "prev", "custom")
CHARGE_KINDS = (LedgerEntry.KIND_QUOTA, LedgerEntry.KIND_CHARGE)


class HistoryError(ValueError):
    def __init__(self, en: str, fa: str, field: str = ""):
        super().__init__(en)
        self.en, self.fa, self.field = en, fa, field

    def payload(self) -> dict:
        return {"detail": self.en, "detail_fa": self.fa, "field": self.field}


# ------------------------------------------------------------------ periods (Tehran days, Jalali months)
def jmonth(d: date) -> tuple[int, int]:
    j = jdatetime.date.fromgregorian(date=d)
    return j.year, j.month


def jmonth_bounds(jy: int, jm: int) -> tuple[date, date]:
    start = jdatetime.date(jy, jm, 1).togregorian()
    nxt = jdatetime.date(jy + (jm == 12), 1 if jm == 12 else jm + 1, 1).togregorian()
    return start, nxt - timedelta(days=1)


def prev_jmonth(jy: int, jm: int) -> tuple[int, int]:
    return (jy - 1, 12) if jm == 1 else (jy, jm - 1)


def bounds(period: str, frm=None, to=None, today: date | None = None) -> tuple[date, date]:
    today = today or tehran_today()
    if period == "d7":
        return today - timedelta(days=6), today
    if period == "month":
        return jmonth_bounds(*jmonth(today))[0], today
    if period == "prev":
        return jmonth_bounds(*prev_jmonth(*jmonth(today)))
    if period == "custom":
        a, b = parse_day(frm), parse_day(to)
        if a is None or b is None:
            raise HistoryError("pick both dates (1405/08/01 or 2026-10-23)", "هر دو تاریخ را وارد کنید (مثلاً 1405/08/01)", "from")
        if a > b:
            raise HistoryError("the start date is after the end date", "تاریخ شروع بعد از تاریخ پایان است", "from")
        if (b - a).days > 3660:
            raise HistoryError("at most 10 years", "حداکثر ۱۰ سال", "to")
        return a, b
    raise HistoryError(f"period must be one of {', '.join(PERIODS)}", "بازهٔ نامعتبر", "period")


# ------------------------------------------------------------------ sums
def _entries(names, to: date):
    return list(LedgerEntry.objects.filter(admin_username__in=list(names), voided=False, date__lte=to)
                .only("admin_username", "kind", "amount", "gb", "date"))


def _empty() -> dict:
    return {"gb": D0, "charged": D0, "adjustments": D0, "paid": D0, "invoiced": D0, "opening": D0, "closing": D0,
            "new_users": None}


def _seen_since():
    first = AgencyUserSeen.objects.order_by("first_seen_at").values_list("first_seen_at", flat=True).first()
    return first


def _fold(entries, frm: date, to: date) -> dict:
    t = _empty()
    for e in entries:
        if e.date < frm:
            t["opening"] += e.signed_amount
            continue
        if e.date > to:
            continue
        if e.kind in CHARGE_KINDS:
            t["charged"] += e.amount
            t["gb"] += e.gb or D0
        elif e.kind == LedgerEntry.KIND_ADJUST:
            t["adjustments"] += e.amount
        elif e.kind == LedgerEntry.KIND_PAYMENT:
            t["paid"] += e.amount
    t["closing"] = t["opening"] + t["charged"] + t["adjustments"] - t["paid"]
    return t


def _invoiced(names, frm: date, to: date) -> Decimal:
    qs = (AgencyInvoice.objects.filter(admin_username__in=list(names), created_at__gte=tehran_day_start(frm),
                                       created_at__lte=tehran_day_end(to)).exclude(status=AgencyInvoice.VOIDED))
    return sum((i.amount for i in qs.only("amount")), D0)


def _new_users(names, frm: date, to: date, since) -> int | None:
    if since is None or tehran_day_end(to) < since:
        return None                                  # no record covers this period (before v1.54's first sync)
    return AgencyUserSeen.objects.filter(admin_username__in=list(names), first_seen_at__gte=tehran_day_start(frm),
                                         first_seen_at__lte=tehran_day_end(to)).count()


def summary(names, frm: date, to: date, *, _entries_cache=None, _since=None) -> dict:
    names = list(names)
    t = _fold(_entries_cache if _entries_cache is not None else _entries(names, to), frm, to)
    t["invoiced"] = _invoiced(names, frm, to)
    t["new_users"] = _new_users(names, frm, to, _since if _since is not None else _seen_since())
    return t


def per_admin(names, frm: date, to: date) -> list[dict]:
    names = sorted(set(names), key=str.lower)
    entries = _entries(names, to)
    by = {}
    for e in entries:
        by.setdefault(e.admin_username, []).append(e)
    since = _seen_since()
    archived = set(PanelAdmin.all_objects.filter(username__in=names, archived_at__isnull=False)
                   .values_list("username", flat=True))
    rows = []
    for n in names:
        s = summary([n], frm, to, _entries_cache=by.get(n, []), _since=since)
        rows.append({"username": n, "archived": n in archived, **s})
    return rows


def monthly(names, months: int = 12, today: date | None = None) -> list[dict]:
    """The last `months` Jalali months (newest first), the current one up to today."""
    today = today or tehran_today()
    names = list(names)
    entries = _entries(names, today)
    since = _seen_since()
    out, (jy, jm) = [], jmonth(today)
    for _ in range(months):
        a, b = jmonth_bounds(jy, jm)
        b = min(b, today)
        s = summary(names, a, b, _entries_cache=entries, _since=since)
        out.append({"key": f"{jy}/{jm:02d}", "from": a, "to": b, **s})
        jy, jm = prev_jmonth(jy, jm)
    return out


def report(names, period: str = "month", frm=None, to=None, *, scope: dict | None = None, admins_table: bool = True) -> dict:
    a, b = bounds(period, frm, to)
    names = sorted(set(names), key=str.lower)
    since = _seen_since()
    return {
        "scope": scope or {}, "period": period, "from": a, "to": b, "from_jalali": jalali_day(a), "to_jalali": jalali_day(b),
        "totals": summary(names, a, b, _since=since), "admins": per_admin(names, a, b) if admins_table and len(names) > 1 else [],
        "monthly": monthly(names), "new_users_since": since, "admin_count": len(names),
    }


def all_usernames() -> list[str]:
    """Every agency admin that ever had a row or a ledger line (archived ones too)."""
    return sorted(set(PanelAdmin.all_objects.values_list("username", flat=True))
                  | set(LedgerEntry.objects.values_list("admin_username", flat=True).distinct()), key=str.lower)


# ------------------------------------------------------------------ export
COLS = ("gb", "charged", "adjustments", "paid", "invoiced", "opening", "closing", "new_users")
HEAD = {
    "fa": {"what": "عنوان", "gb": "حجم فروخته‌شده (GB)", "charged": "فروش / شارژ (تومان)", "adjustments": "اصلاحیه‌ها (تومان)",
           "paid": "پرداخت‌شده (تومان)", "invoiced": "فاکتورشده (تومان)", "opening": "مانده ابتدای بازه", "closing": "مانده پایان بازه",
           "new_users": "کاربران جدید", "total": "جمع بازه", "month": "ماه", "admin": "ادمین", "archived": " (بایگانی)"},
    "en": {"what": "Item", "gb": "Volume sold (GB)", "charged": "Sales / charged (T)", "adjustments": "Adjustments (T)",
           "paid": "Paid (T)", "invoiced": "Invoiced (T)", "opening": "Opening balance", "closing": "Closing balance",
           "new_users": "New users", "total": "Period total", "month": "Month", "admin": "Admin", "archived": " (archived)"},
}


def _cells(s: dict) -> list:
    out = []
    for c in COLS:
        v = s.get(c)
        out.append("" if v is None else (float(round(v, 2)) if c == "gb" else int(v)))
    return out


def export_rows(rep: dict, lang: str = "fa") -> list[list]:
    h = HEAD.get(lang, HEAD["fa"])
    period = f"{rep['from_jalali']} – {rep['to_jalali']}" if lang == "fa" else f"{rep['from']} – {rep['to']}"
    rows = [[h["what"], *[h[c] for c in COLS]], [f"{h['total']} {period}", *_cells(rep["totals"])]]
    if rep["admins"]:
        rows.append([])
        rows.append([h["admin"], *[h[c] for c in COLS]])
        rows += [[r["username"] + (h["archived"] if r["archived"] else ""), *_cells(r)] for r in rep["admins"]]
    rows.append([])
    rows.append([h["month"], *[h[c] for c in COLS]])
    rows += [[m["key"], *_cells(m)] for m in rep["monthly"]]
    return rows
