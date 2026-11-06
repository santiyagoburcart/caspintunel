"""Accounting ledger of the agency panel (caspintunel addition, not PAMP).

Charging basis (a) — "charge when quota is granted": when an admin's limit is
RAISED through the agency panel, a quota charge = increase in GB × the price
per GB valid on that day. Additive only: it reads the limit change, it never
changes PAMP's numbers.

  * GB uses PAMP's unit (1024**3 bytes); the amount is rounded half-up to whole tomans.
  * An unlimited admin counts as its LAST FINITE limit (PanelAdmin.last_limit_bytes,
    0 only if it never had one): giving it a limit again charges only new − last.
    Lowering a limit or removing it creates no automatic credit (use an adjustment).
  * v1.34: no price for the day → NO charge (billing.NoPrice «قیمت هر گیگ برای این ادمین
    تعریف نشده» + a Telegram to staff); callers check the price BEFORE changing PasarGuard
    (billing.ensure_price). Every charge issues an invoice (billing.issue_for_entry).
  * Balance = charges + adjustments − payments (voided entries excluded).
"""
from __future__ import annotations

import csv
import io
from datetime import date as date_cls
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Case, DecimalField, F, Sum, When

from .models import AdminPrice, LedgerEntry
from .notes import to_fa

GB = Decimal(1024 ** 3)


def today() -> date_cls:
    """Today in Tehran (the server runs in UTC: 00:00–03:30 Tehran was still "yesterday" — v1.42.1)."""
    from apps.common.jalali import tehran_today

    return tehran_today()


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
                        day: date_cls | None = None, note: str = "", invoice: bool = True) -> LedgerEntry | None:
    """Called after a successful limit change on the panel (or when a group manager's
    volume is approved — then `day` is the day the volume was given). Only an increase charges.
    Issues the invoice unless `invoice=False` (the caller issues it with its request)."""
    from .billing import issue_for_entry, missing_price

    old, new = int(old_limit_bytes or 0), int(new_limit_bytes or 0)
    if new <= old:
        return None
    gb = Decimal(new - old) / GB
    day = day or today()
    price = price_at(username, day)
    if not price:          # callers check first; this only guards a path that forgot to
        raise missing_price(username, gb.quantize(Decimal("0.01")))
    amount = _round(gb * price.price_per_gb)
    e = LedgerEntry.objects.create(
        admin_username=username, kind=LedgerEntry.KIND_QUOTA, amount=amount, date=day,
        gb=gb.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), price_per_gb=price.price_per_gb,
        old_limit_bytes=old, new_limit_bytes=new, created_by=by[:150], note=note[:255])
    if invoice:
        issue_for_entry(e, by=by)
    return e


@transaction.atomic
def add_entry(username: str, kind: str, amount, day: date_cls, *, method: str = "", note: str = "", by: str = "",
              gb=None, direction: str | None = None, settle: str | None = None, invoice_ids=None) -> LedgerEntry:
    """`direction` (v1.33, adjustments): "increase" = owes more, "decrease" = owes less; the
    amount is then a positive number and the sign comes from the direction. Without it the
    old signed amount is still accepted (API compatibility).
    v1.35.1: a payment / decrease settles invoices — `settle` "auto" (oldest first, default),
    "selected" (`invoice_ids`, in that order) or "none"; then the invariant (allocation.enforce)."""
    if kind not in (LedgerEntry.KIND_CHARGE, LedgerEntry.KIND_ADJUST, LedgerEntry.KIND_PAYMENT):
        raise ValueError("kind must be manual_charge, adjustment or payment")
    amount = _round(Decimal(str(amount)))
    if kind == LedgerEntry.KIND_ADJUST and direction not in (None, ""):
        if direction not in ("increase", "decrease"):
            raise ValueError("direction must be increase or decrease")
        if amount <= 0:
            raise ValueError("enter a positive amount — the direction button sets more / less debt")
        if direction == "decrease":
            amount = -amount
    if kind != LedgerEntry.KIND_ADJUST and amount <= 0:
        raise ValueError("amount must be positive")
    if kind == LedgerEntry.KIND_ADJUST and amount == 0:
        raise ValueError("an adjustment cannot be zero")
    if kind == LedgerEntry.KIND_PAYMENT and method not in dict(LedgerEntry.METHODS):
        raise ValueError("unknown payment method")
    gb_d = Decimal(str(gb)) if gb not in (None, "") else None
    price = None
    if kind == LedgerEntry.KIND_CHARGE and gb_d:
        # v1.34: a charge with GB is GB × the admin's price of that day (no price → no charge)
        from .billing import ensure_price

        if gb_d <= 0:
            raise ValueError("GB must be positive")
        price = ensure_price(username, gb_d, day, context="manual charge").price_per_gb
        amount = _round(gb_d * price)
    e = LedgerEntry.objects.create(
        admin_username=username, kind=kind, amount=amount, date=day, method=method if kind == LedgerEntry.KIND_PAYMENT else "",
        note=note[:255], created_by=by[:150], gb=gb_d, price_per_gb=price)
    if kind == LedgerEntry.KIND_CHARGE:
        from .billing import issue_for_entry

        issue_for_entry(e, by=by)
    else:
        from . import allocation

        allocation.apply_entry(e, settle=settle or "auto", invoice_ids=invoice_ids, by=by)
    return e


@transaction.atomic
def void(entry_id: int, reason: str, by: str = "", _from_invoice: bool = False) -> LedgerEntry:
    e = LedgerEntry.objects.select_for_update().get(pk=entry_id)
    if e.voided:
        raise ValueError("already voided")
    if not reason.strip():
        raise ValueError("a reason is required")
    if not _from_invoice and e.invoices.filter(status__in=("paid", "pending")).exists():
        raise ValueError("this charge's invoice is paid or under review — void the payment first")
    e.voided, e.void_reason = True, f"{reason.strip()[:200]} ({by})" if by else reason.strip()[:255]
    e.save(update_fields=["voided", "void_reason"])
    if not _from_invoice:
        from . import allocation
        from .billing import on_ledger_void

        on_ledger_void(e)        # its unpaid invoice is voided too
        allocation.on_entry_void(e)   # v1.35.1: what this payment / adjustment settled is open again
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
    from .models import AgencyInvoiceAllocation

    entries = LedgerEntry.objects.filter(admin_username=username).order_by("date", "id")
    settles: dict[int, list] = {}
    for a in (AgencyInvoiceAllocation.objects.filter(ledger_entry__admin_username=username, released=False)
              .values("ledger_entry_id", "invoice_id", "amount")):
        settles.setdefault(a["ledger_entry_id"], []).append({"invoice": f"INV-{a['invoice_id']:06d}", "amount": a["amount"]})
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
                     "new_limit_bytes": e.new_limit_bytes, "method": e.method, "note": e.note, "note_fa": to_fa(e.note),
                     "old_limit_fmt": _fmt(e.old_limit_bytes), "new_limit_fmt": _fmt(e.new_limit_bytes),
                     "created_by": e.created_by, "voided": e.voided, "void_reason": e.void_reason,
                     "balance": running, "settles": settles.get(e.id, [])})
    cur = price_at(username)
    from . import allocation

    return {
        "invoices_mismatch": allocation.mismatch(username),
        "username": username, "charges": charges, "payments": payments, "balance": charges - payments,
        "entries": rows,
        "price": {"price_per_gb": cur.price_per_gb, "valid_from": cur.valid_from} if cur else None,
        "prices": [{"id": p.id, "price_per_gb": p.price_per_gb, "valid_from": p.valid_from, "note": p.note,
                    "note_fa": to_fa(p.note),
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
