"""Accounting ledger of the agency panel (caspintunel addition, not PAMP).

Charging basis (a) — "charge when quota is granted": when an admin's limit is
RAISED through the agency panel, a quota charge = increase in GB × the price
per GB valid on that day. Additive only: it reads the limit change, it never
changes PAMP's numbers.

  * GB uses PAMP's unit (1024**3 bytes); the amount is rounded half-up to whole tomans.
  * An unlimited admin counts as its LAST FINITE limit (PanelAdmin.last_limit_bytes,
    0 only if it never had one): giving it a limit again charges only new − last.
    Lowering a limit or removing it creates no automatic credit (use an adjustment).
  * No price set for the day → the charge is still recorded (amount 0, noted) so
    the grant is never lost; fix it with an adjustment.
  * Balance = charges + adjustments − payments (voided entries excluded).
"""
from __future__ import annotations

import csv
import io
from datetime import date as date_cls
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Case, DecimalField, F, Sum, When
from django.utils import timezone

from .models import AdminPrice, LedgerEntry

GB = Decimal(1024 ** 3)


def today() -> date_cls:
    return timezone.localdate()


def price_at(username: str, day: date_cls | None = None) -> AdminPrice | None:
    return (AdminPrice.objects.filter(admin_username=username, valid_from__lte=day or today())
            .order_by("-valid_from", "-id").first())


def set_price(username: str, price, valid_from: date_cls, note: str = "", by: str = "") -> AdminPrice:
    price = Decimal(str(price))
    if price < 0:
        raise ValueError("price must be zero or more")
    return AdminPrice.objects.create(admin_username=username, price_per_gb=price.quantize(Decimal(1)),
                                     valid_from=valid_from, note=note[:255], created_by=by[:150])


def _round(x: Decimal) -> Decimal:
    return x.quantize(Decimal(1), rounding=ROUND_HALF_UP)


def quote_quota_charge(username: str, old_limit_bytes: int, new_limit_bytes: int,
                       day: date_cls | None = None) -> dict | None:
    """The charge an increase would create today (or on `day`); None = no charge."""
    old, new = int(old_limit_bytes or 0), int(new_limit_bytes or 0)
    if new <= old:
        return None
    gb = Decimal(new - old) / GB
    price = price_at(username, day or today())
    return {"gb": gb.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), "price_per_gb": price.price_per_gb if price else None,
            "amount": _round(gb * price.price_per_gb) if price else Decimal(0)}


def record_quota_charge(username: str, old_limit_bytes: int, new_limit_bytes: int, by: str = "",
                        day: date_cls | None = None, note: str = "") -> LedgerEntry | None:
    """Called after a successful limit change on the panel (or when a group manager's
    volume is approved — then `day` is the day the volume was given). Only an increase charges."""
    old, new = int(old_limit_bytes or 0), int(new_limit_bytes or 0)
    if new <= old:
        return None
    gb = Decimal(new - old) / GB
    day = day or today()
    price = price_at(username, day)
    amount = _round(gb * price.price_per_gb) if price else Decimal(0)
    if not price:
        note = (note + " · " if note else "") + "no price per GB set for this date — add an adjustment"
    return LedgerEntry.objects.create(
        admin_username=username, kind=LedgerEntry.KIND_QUOTA, amount=amount, date=day,
        gb=gb.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), price_per_gb=price.price_per_gb if price else None,
        old_limit_bytes=old, new_limit_bytes=new, created_by=by[:150], note=note[:255])


def add_entry(username: str, kind: str, amount, day: date_cls, *, method: str = "", note: str = "", by: str = "",
              gb=None) -> LedgerEntry:
    if kind not in (LedgerEntry.KIND_CHARGE, LedgerEntry.KIND_ADJUST, LedgerEntry.KIND_PAYMENT):
        raise ValueError("kind must be manual_charge, adjustment or payment")
    amount = _round(Decimal(str(amount)))
    if kind != LedgerEntry.KIND_ADJUST and amount <= 0:
        raise ValueError("amount must be positive")
    if kind == LedgerEntry.KIND_ADJUST and amount == 0:
        raise ValueError("an adjustment cannot be zero")
    if kind == LedgerEntry.KIND_PAYMENT and method not in dict(LedgerEntry.METHODS):
        raise ValueError("unknown payment method")
    return LedgerEntry.objects.create(
        admin_username=username, kind=kind, amount=amount, date=day, method=method if kind == LedgerEntry.KIND_PAYMENT else "",
        note=note[:255], created_by=by[:150], gb=Decimal(str(gb)) if gb not in (None, "") else None)


@transaction.atomic
def void(entry_id: int, reason: str, by: str = "") -> LedgerEntry:
    e = LedgerEntry.objects.select_for_update().get(pk=entry_id)
    if e.voided:
        raise ValueError("already voided")
    if not reason.strip():
        raise ValueError("a reason is required")
    e.voided, e.void_reason = True, f"{reason.strip()[:200]} ({by})" if by else reason.strip()[:255]
    e.save(update_fields=["voided", "void_reason"])
    return e


_SIGNED = Case(When(kind=LedgerEntry.KIND_PAYMENT, then=-F("amount")), default=F("amount"),
               output_field=DecimalField(max_digits=16, decimal_places=0))


def balances() -> dict[str, Decimal]:
    rows = (LedgerEntry.objects.filter(voided=False).values("admin_username")
            .annotate(b=Sum(_SIGNED)))
    return {r["admin_username"]: r["b"] or Decimal(0) for r in rows}


def _fmt(b):
    from .models import _fmt_bytes          # PAMP's own formatter (1024-based)

    return None if b is None else ("Unlimited" if b == 0 else _fmt_bytes(b))


def statement(username: str) -> dict:
    entries = LedgerEntry.objects.filter(admin_username=username).order_by("date", "id")
    running, rows = Decimal(0), []
    charges = payments = Decimal(0)
    for e in entries:
        if not e.voided:
            running += e.signed_amount
            if e.kind == LedgerEntry.KIND_PAYMENT:
                payments += e.amount
            else:
                charges += e.amount
        rows.append({"id": e.id, "date": e.date, "kind": e.kind, "amount": e.amount, "signed": e.signed_amount,
                     "gb": e.gb, "price_per_gb": e.price_per_gb, "old_limit_bytes": e.old_limit_bytes,
                     "new_limit_bytes": e.new_limit_bytes, "method": e.method, "note": e.note,
                     "old_limit_fmt": _fmt(e.old_limit_bytes), "new_limit_fmt": _fmt(e.new_limit_bytes),
                     "created_by": e.created_by, "voided": e.voided, "void_reason": e.void_reason,
                     "balance": running})
    cur = price_at(username)
    return {
        "username": username, "charges": charges, "payments": payments, "balance": charges - payments,
        "entries": rows,
        "price": {"price_per_gb": cur.price_per_gb, "valid_from": cur.valid_from} if cur else None,
        "prices": [{"id": p.id, "price_per_gb": p.price_per_gb, "valid_from": p.valid_from, "note": p.note,
                    "created_by": p.created_by} for p in AdminPrice.objects.filter(admin_username=username)],
    }


def statement_csv(username: str) -> str:
    """UTF-8 CSV (with BOM for Excel), Jalali dates, Latin digits."""
    from apps.common.jalali import to_jalali_str

    st = statement(username)
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf)
    w.writerow(["date (jalali)", "kind", "gb", "price_per_gb", "amount_toman", "signed", "balance", "method",
                "note", "voided"])
    for r in st["entries"]:
        w.writerow([to_jalali_str(r["date"], "%Y/%m/%d"), r["kind"], r["gb"] or "", r["price_per_gb"] or "", r["amount"],
                    r["signed"], r["balance"], r["method"], r["note"], "voided: " + r["void_reason"] if r["voided"] else ""])
    w.writerow([])
    w.writerow(["charges", st["charges"]]); w.writerow(["payments", st["payments"]]); w.writerow(["balance", st["balance"]])
    return buf.getvalue()
