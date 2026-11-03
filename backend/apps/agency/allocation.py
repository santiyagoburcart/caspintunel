"""Which money settles which agency invoice (v1.35.1, docs/agency.md → "Invoices and the ledger").

An invoice is settled by allocation rows (`AgencyInvoiceAllocation`), never by flipping its status:
  * payment     an agency checkout (AgencyPayment approved — billing.approve_payment)
  * manual      a staff «ثبت پرداخت» ledger entry — staff pick the invoices, or oldest first (partial allowed)
  * adjustment  an «اصلاحیه · کاهش بدهی» — selected invoices, oldest first, or none (then only the invariant)
  * outside     «تسویه خارج از سیستم»: paid outside (e.g. older months) — no ledger entry, the charge stays
  * balance     the admin's ledger balance already covered it (credit without one source entry)
`paid_amount` = active allocations; paid in full → status paid (`settled_via` says how); partially → still
unpaid with paid / remaining. «افزایش بدهی» never touches invoices.

INVARIANT: an admin's open (unpaid + under review) invoice remainder never exceeds the ledger debt
(max(0, balance)). `enforce` runs after every ledger change and every new invoice: any excess is allocated
to unpaid invoices oldest first, attributed to the payment / decrease entries since the first invoice that
still have unallocated credit (oldest first), then to "balance". Voiding a source entry releases its rows.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import AgencyInvoice, AgencyInvoiceAllocation as Alloc, AgencyPayment, LedgerEntry

D0 = Decimal(0)
OPEN = (AgencyInvoice.UNPAID, AgencyInvoice.PENDING)
SOURCE_SKEW_SECONDS = 120


def remaining(inv: AgencyInvoice) -> Decimal:
    if inv.status not in OPEN:
        return D0
    return max(D0, inv.amount - (inv.paid_amount or D0))


def entry_kind(entry: LedgerEntry | None) -> str:
    if entry is None:
        return Alloc.BALANCE
    return Alloc.MANUAL if entry.kind == LedgerEntry.KIND_PAYMENT else Alloc.ADJUSTMENT


def is_reducing(entry: LedgerEntry) -> bool:
    return entry.kind == LedgerEntry.KIND_PAYMENT or (entry.kind == LedgerEntry.KIND_ADJUST and entry.amount < 0)


def refresh(inv: AgencyInvoice) -> AgencyInvoice:
    """Recompute paid_amount / settled_via / status from the active allocations."""
    rows = list(inv.allocations.filter(released=False).values_list("kind", "amount"))
    paid = sum((a for _, a in rows), D0)
    kinds = {k for k, _ in rows}
    inv.paid_amount = paid
    inv.settled_via = "" if not kinds else (kinds.pop() if len(kinds) == 1 else "mixed")
    if inv.status != AgencyInvoice.VOIDED:
        if paid >= inv.amount and inv.amount > 0:
            if inv.status != AgencyInvoice.PAID:
                inv.status, inv.paid_at = AgencyInvoice.PAID, timezone.now()
        elif inv.status == AgencyInvoice.PAID:          # a source was voided → open again
            inv.status, inv.paid_at = AgencyInvoice.UNPAID, None
    inv.save(update_fields=["paid_amount", "settled_via", "status", "paid_at"])
    return inv


def _add(inv: AgencyInvoice, amount: Decimal, kind: str, *, entry=None, payment=None, auto=False, note="", by="") -> Alloc:
    a = Alloc.objects.create(invoice=inv, kind=kind, amount=amount, ledger_entry=entry, agency_payment=payment,
                             auto=auto, note=note[:255], created_by=(by or "")[:150])
    refresh(inv)
    return a


def _cancel_checkouts(invoice_ids) -> None:
    from .billing import _cancel_open_payments

    if invoice_ids:
        _cancel_open_payments(list(invoice_ids))


def unpaid_invoices(username: str, *, lock: bool = True) -> list[AgencyInvoice]:
    qs = AgencyInvoice.objects.filter(admin_username=username, status=AgencyInvoice.UNPAID).order_by("created_at", "id")
    return list(qs.select_for_update() if lock else qs)


class AllocationError(ValueError):
    pass


def allocate(username: str, amount, *, kind: str, entry: LedgerEntry | None = None, invoice_ids=None,
             by: str = "", note: str = "") -> list[tuple[AgencyInvoice, Decimal]]:
    """Spend `amount` on this admin's unpaid invoices: `invoice_ids` in that order (staff choice), else
    oldest first. The last one may be partial. Invoices under review (agency payment pending) are skipped."""
    left = Decimal(amount)
    if left <= 0:
        return []
    invs = unpaid_invoices(username)
    auto = not invoice_ids
    if invoice_ids:
        want = [int(i) for i in invoice_ids]
        by_id = {i.id: i for i in invs}
        bad = [i for i in want if i not in by_id]
        if bad:
            others = AgencyInvoice.objects.filter(pk__in=bad)
            nums = ", ".join(o.number for o in others) or ", ".join(map(str, bad))
            raise AllocationError(f"these invoices are not unpaid invoices of {username}: {nums}")
        invs = [by_id[i] for i in dict.fromkeys(want)]
    out = []
    for inv in invs:
        if left <= 0:
            break
        take = min(left, remaining(inv))
        if take <= 0:
            continue
        _add(inv, take, kind, entry=entry, auto=auto, by=by, note=note)
        out.append((inv, take))
        left -= take
    _cancel_checkouts([i.id for i, _ in out])          # an unfinished checkout has the old amount
    return out


def balance_of(username: str) -> Decimal:
    from .ledger import _SIGNED

    return (LedgerEntry.objects.filter(admin_username=username, voided=False)
            .aggregate(b=Sum(_SIGNED))["b"] or D0)


def open_remaining(username: str) -> Decimal:
    return sum((remaining(i) for i in AgencyInvoice.objects.filter(admin_username=username, status__in=OPEN)), D0)


def outside_total(username: str) -> Decimal:
    return (Alloc.objects.filter(invoice__admin_username=username, kind=Alloc.OUTSIDE, released=False)
            .exclude(invoice__status=AgencyInvoice.VOIDED).aggregate(s=Sum("amount"))["s"] or D0)


def entry_credit(entry: LedgerEntry) -> Decimal:
    used = entry.allocations.filter(released=False).aggregate(s=Sum("amount"))["s"] or D0
    return max(D0, abs(entry.amount) - used)


def _sources(username: str) -> list[LedgerEntry]:
    """Payment / decrease entries since this admin's first invoice that still have unallocated credit."""
    first = (AgencyInvoice.objects.filter(admin_username=username).order_by("created_at", "id")
             .values_list("created_at", flat=True).first())
    if first is None:
        return []
    since = first - timedelta(seconds=SOURCE_SKEW_SECONDS)
    qs = (LedgerEntry.objects.filter(admin_username=username, voided=False, created_at__gte=since)
          .filter(kind__in=(LedgerEntry.KIND_PAYMENT, LedgerEntry.KIND_ADJUST)).order_by("created_at", "id"))
    return [e for e in qs if is_reducing(e) and entry_credit(e) > 0]


@dataclass
class Step:
    invoice: AgencyInvoice
    amount: Decimal
    kind: str
    entry: LedgerEntry | None


def plan(username: str) -> dict:
    """Read-only: what `enforce` would allocate now (also the data-fix preview)."""
    bal = balance_of(username)
    invs = list(AgencyInvoice.objects.filter(admin_username=username, status__in=OPEN).order_by("created_at", "id"))
    unpaid_total = sum((remaining(i) for i in invs), D0)
    excess = unpaid_total - max(D0, bal)
    steps: list[Step] = []
    if excess > 0:
        credits = [(e, entry_credit(e)) for e in _sources(username)]
        rem = {i.id: remaining(i) for i in invs}
        left = excess
        for inv in [i for i in invs if i.status == AgencyInvoice.UNPAID]:
            while left > 0 and rem[inv.id] > 0:
                src = next(((k, c) for k, c in enumerate(credits) if c[1] > 0), None)
                if src is None:
                    take = min(left, rem[inv.id])
                    steps.append(Step(inv, take, Alloc.BALANCE, None))
                else:
                    k, (e, c) = src
                    take = min(left, rem[inv.id], c)
                    credits[k] = (e, c - take)
                    steps.append(Step(inv, take, entry_kind(e), e))
                rem[inv.id] -= take
                left -= take
            if left <= 0:
                break
    return {"admin": username, "balance": bal, "open": unpaid_total, "excess": max(D0, excess), "steps": steps,
            "left": max(D0, excess - sum((s.amount for s in steps), D0))}


@transaction.atomic
def enforce(username: str, *, by: str = "system") -> list[Step]:
    """Keep the invariant (see the module doc). Must run inside a transaction."""
    if not AgencyInvoice.objects.filter(admin_username=username, status__in=OPEN).exists():
        return []
    unpaid_invoices(username)                      # lock this admin's unpaid invoices
    p = plan(username)
    for s in p["steps"]:
        s.invoice.refresh_from_db()
        _add(s.invoice, s.amount, s.kind, entry=s.entry, auto=True, by=by,
             note="auto: unpaid invoices may not exceed the ledger balance")
    _cancel_checkouts([s.invoice.id for s in p["steps"]])
    return p["steps"]


def mismatch(username: str) -> dict | None:
    """For the admin page warning: open invoices larger than the ledger debt."""
    bal, op = balance_of(username), open_remaining(username)
    if op > max(D0, bal):
        return {"open": op, "balance": bal, "diff": op - max(D0, bal)}
    return None


def release(qs, reason: str) -> list[int]:
    ids = list(qs.filter(released=False).values_list("invoice_id", flat=True))
    qs.filter(released=False).update(released=True, released_at=timezone.now(), release_reason=reason[:255])
    for inv in AgencyInvoice.objects.filter(pk__in=set(ids)):
        refresh(inv)
    return ids


@transaction.atomic
def on_entry_void(entry: LedgerEntry) -> None:
    """A voided payment / adjustment no longer settles anything; a voided charge may free credit."""
    release(entry.allocations.all(), f"ledger entry {entry.id} voided")
    enforce(entry.admin_username)


def on_invoice_void(inv: AgencyInvoice) -> None:
    release(inv.allocations.all(), f"invoice {inv.number} voided")


@transaction.atomic
def settle_outside(invoice_id: int, *, note: str = "", by: str = "") -> AgencyInvoice:
    """«تسویه خارج از سیستم»: the rest of the invoice is marked settled; its charge and the ledger stay."""
    from .billing import BillingError

    inv = AgencyInvoice.objects.select_for_update().filter(pk=invoice_id).first()
    if inv is None:
        raise BillingError("invoice not found", "not_found")
    if inv.status != AgencyInvoice.UNPAID:
        raise BillingError(f"only an unpaid invoice can be settled (this one is {inv.status})", "conflict",
                           fa="فقط فاکتور پرداخت‌نشده تسویه می‌شود")
    rest = remaining(inv)
    _add(inv, rest, Alloc.OUTSIDE, by=by, note=(note or "paid outside the system").strip())
    _cancel_checkouts([inv.id])
    return inv


def apply_entry(entry: LedgerEntry, *, settle: str = "auto", invoice_ids=None, by: str = "") -> list:
    """After a new ledger entry: a payment / decrease settles invoices (chosen, oldest first, or none),
    then the invariant. Anything else only runs the invariant."""
    done = []
    if is_reducing(entry):
        if settle not in ("auto", "selected", "none"):
            raise AllocationError("settle must be auto, selected or none")
        if settle == "selected" and not invoice_ids:
            raise AllocationError("choose at least one invoice")
        if settle != "none":
            done = allocate(entry.admin_username, abs(entry.amount), kind=entry_kind(entry), entry=entry,
                            invoice_ids=invoice_ids if settle == "selected" else None, by=by)
    elif invoice_ids:
        raise AllocationError("only a payment or a debt decrease can settle invoices")
    enforce(entry.admin_username, by=by or "system")
    return done


def allocate_agency_payment(p: AgencyPayment, entries: dict[str, LedgerEntry], by: str) -> None:
    """An approved checkout settles its invoices (what is still open of them)."""
    touched = set()
    for it in p.items.select_related("invoice"):
        inv = AgencyInvoice.objects.select_for_update().get(pk=it.invoice_id)
        take = min(it.amount, remaining(inv))
        if take > 0:
            _add(inv, take, Alloc.PAYMENT, entry=entries.get(inv.admin_username), payment=p, by=by,
                 note=f"agency payment {p.number}")
            if inv.status == AgencyInvoice.PENDING:           # still short (should not happen) → back to unpaid
                inv.status = AgencyInvoice.UNPAID
                inv.save(update_fields=["status"])
        touched.add(inv.admin_username)
    for n in touched:
        enforce(n, by=by)


def row(a: Alloc) -> dict:
    return {"id": a.id, "kind": a.kind, "amount": a.amount, "auto": a.auto, "entry": a.ledger_entry_id,
            "payment": a.agency_payment.number if a.agency_payment_id else None, "note": a.note,
            "created_by": a.created_by, "created_at": a.created_at}
