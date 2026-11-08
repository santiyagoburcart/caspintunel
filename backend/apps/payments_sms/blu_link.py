"""v1.42.2 Blu deposits ↔ payments («اتصال به سفارش» in the Blu tab).

- `resolve(ref)`: what staff type — an order id (#125 / 125), TX-000050 (a payment), MI-000003 (a manual invoice),
  INV-000012 (an agency invoice) or AP-000014 (an agency payment).
- `candidates(tx)`: what the deposit could belong to — amount within ±20 %, around the deposit time, payer name, the
  bank's tracking / reference number — best first.
- `link(tx, ref, staff, confirm=False)`:
    · target NOT paid yet → approved with this deposit as before (customer: `matching.confirm_blu`; agency:
      `billing.approve_payment(source="blu_auto")`). A deposit that differs from the invoice needs `confirm`; a shorter
      one records the shortfall (e.g. 175,000 paid for a 176,195 order).
    · target ALREADY approved (manual invoice, receipt approved by staff, SMS…) → LINK ONLY: the deposit becomes
      «متصل به پرداخت موجود» (`BluStatus.LINKED`) and the payment shows it. No new approval, nothing counted twice —
      Accounting / Transactions / Analytics count payments, never deposits.
- `unlink(tx, staff)` (Super Admin): undoes a link-only connection (an approval is undone by voiding the payment).
- `auto_link_payment` / `auto_link_agency_payment`: when a payment is approved by any route, an unmatched deposit with
  the same tracking / reference number — or else exactly one with the same amount around that time and the same payer
  name (when both names are known) — is linked automatically. `backfill()` runs the same rule over existing deposits.
"""
from __future__ import annotations

import logging
import re
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.common.models import write_audit

from .checks import normalize_ref
from .models import BluStatus, BluTransaction, Payment, PaymentStatus

log = logging.getLogger("caspintunel")
NEAR = Decimal("0.20")                      # ±20 % for candidates
CANDIDATE_WINDOW = timedelta(days=3)        # around the deposit time
AUTO_WINDOW = timedelta(hours=24)           # auto-link by amount: deposit within 24 h of the approval / entered date
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


class LinkError(Exception):
    def __init__(self, en: str, fa: str, code: str = "invalid", status: int = 400, **extra):
        super().__init__(en)
        self.en, self.fa, self.code, self.status, self.extra = en, fa, code, status, extra

    def payload(self) -> dict:
        return {"detail": self.en, "detail_fa": self.fa, "code": self.code, **self.extra}


# --------------------------------------------------------------------------------------------- targets
class Target:
    """An order (customer) or an agency payment, with what linking needs to know."""

    def __init__(self, *, order=None, agency=None, label: str = ""):
        self.order, self.agency, self.label = order, agency, label

    @property
    def payment(self) -> Payment | None:
        if self.order is None:
            return None
        return Payment.objects.live().filter(order=self.order).first()

    @property
    def paid(self) -> bool:
        if self.agency is not None:
            return self.agency.status == "approved"
        p = self.payment
        return bool(p and p.status == PaymentStatus.APPROVED) or self.order.status in ("paid", "completed")

    @property
    def amount(self) -> Decimal:
        return Decimal(self.agency.amount_unique if self.agency is not None else self.order.amount_unique or self.order.amount)

    def describe(self) -> str:
        return self.label


def resolve(ref) -> Target:
    from apps.agency.models import AgencyInvoice, AgencyPayment
    from apps.orders.models import ManualInvoice, Order

    s = str(ref or "").strip().upper().translate(_DIGITS).replace(" ", "").lstrip("#")
    if not s:
        raise LinkError("enter an order number, TX-, MI-, INV- or AP-", "شماره سفارش، TX-، MI-، INV- یا AP- را وارد کنید",
                        "empty")
    m = re.fullmatch(r"(TX|MI|INV|AP|ORD)?-?0*(\d+)", s)
    if not m:
        raise LinkError(f"unknown reference {ref!r}", f"مرجع «{ref}» شناخته نشد", "unknown")
    kind, n = m.group(1) or "", int(m.group(2))
    if kind == "TX":
        p = Payment.objects.select_related("order").filter(number=n).first() or \
            Payment.objects.select_related("order").filter(pk=n, number__isnull=True).first()
        if p is None or p.order_id is None:
            raise LinkError(f"{s} not found", f"{s} پیدا نشد", "not_found", 404)
        return Target(order=p.order, label=f"{p.tx_number} · order #{p.order_id}")
    if kind == "MI":
        inv = ManualInvoice.objects.filter(pk=n).first()
        if inv is None:
            raise LinkError(f"{s} not found", f"{s} پیدا نشد", "not_found", 404)
        order = inv.order or Order.objects.filter(manual_invoice=inv).order_by("-id").first()
        if order is None:
            raise LinkError(f"{inv.number} has no order to pay yet", f"فاکتور {inv.number} هنوز سفارشی برای پرداخت ندارد",
                            "no_order")
        return Target(order=order, label=f"{inv.number} · order #{order.id}")
    if kind in ("INV", "AP"):
        if kind == "AP":
            ap = AgencyPayment.objects.filter(pk=n).first()
        else:
            inv = AgencyInvoice.objects.filter(pk=n).first()
            if inv is None:
                raise LinkError(f"{s} not found", f"{s} پیدا نشد", "not_found", 404)
            ap = (AgencyPayment.objects.filter(items__invoice=inv).exclude(status="cancelled")
                  .order_by("-created_at").first())
            if ap is None:
                raise LinkError(f"{inv.number} has no agency payment — the payer starts one in the portal",
                                f"برای {inv.number} پرداختی ثبت نشده — پرداخت‌کننده باید از پرتال آن را شروع کند", "no_payment")
        if ap is None:
            raise LinkError(f"{s} not found", f"{s} پیدا نشد", "not_found", 404)
        return Target(agency=ap, label=f"{ap.number} · {ap.payer_username}")
    order = Order.objects.filter(pk=n).first()
    if order is None:
        raise LinkError(f"order #{n} not found", f"سفارش #{n} پیدا نشد", "not_found", 404)
    return Target(order=order, label=f"order #{order.id}")


# --------------------------------------------------------------------------------------------- candidates
def _name_key(v: str) -> str:
    return re.sub(r"[\W_]+", "", (v or "").translate(_DIGITS)).replace("ي", "ی").replace("ك", "ک").casefold()


def names_match(a: str, b: str) -> bool:
    """Payer name on the deposit vs the customer / payer: equal or one contains the other (both at least 3 letters)."""
    x, y = _name_key(a), _name_key(b)
    return len(x) >= 3 and len(y) >= 3 and (x in y or y in x)


def _refs(tx) -> set[str]:
    return {r for r in (normalize_ref(tx.reference), normalize_ref(tx.receipt)) if len(r) >= 6}


def ref_match(tx, raw) -> bool:
    r = normalize_ref(raw)
    if len(r) < 6:
        return False
    return any(r == x or (len(r) >= 6 and x.endswith(r)) or r.endswith(x) for x in _refs(tx))


def candidates(tx, q: str = "", limit: int = 12) -> list[dict]:
    """Orders / manual invoices / agency payments this deposit could belong to, best first."""
    from apps.agency.models import AgencyPayment
    from apps.orders.models import Order

    out: list[dict] = []
    if q.strip():
        try:
            t = resolve(q)
            out.append(_cand(tx, t, why=["typed"]))
        except LinkError:
            pass
    amt = Decimal(tx.amount_toman or 0)
    if amt > 0:
        lo, hi = amt * (1 - NEAR), amt * (1 + NEAR)
        at = tx.occurred_at
        orders = (Order.objects.select_related("user", "manual_invoice")
                  .filter(amount_unique__gte=lo, amount_unique__lte=hi,
                          created_at__gte=at - CANDIDATE_WINDOW, created_at__lte=at + CANDIDATE_WINDOW)
                  .exclude(status__in=("cancelled",)).order_by("-created_at")[:60])
        for o in orders:
            label = f"{o.manual_invoice.number} · order #{o.id}" if o.manual_invoice_id else f"order #{o.id}"
            out.append(_cand(tx, Target(order=o, label=label)))
        aps = AgencyPayment.objects.filter(amount_unique__gte=lo, amount_unique__lte=hi,
                                           created_at__gte=at - CANDIDATE_WINDOW,
                                           created_at__lte=at + CANDIDATE_WINDOW).exclude(status="cancelled")[:30]
        for ap in aps:
            out.append(_cand(tx, Target(agency=ap, label=f"{ap.number} · {ap.payer_username}")))
        # any approved payment carrying this tracking / reference number (e.g. a manual invoice entered by hand)
        refs = _refs(tx)
        if refs:
            for p in Payment.objects.live().select_related("order", "order__manual_invoice").filter(receipt_ref__in=refs)[:10]:
                if p.order_id:
                    o = p.order
                    label = f"{o.manual_invoice.number} · order #{o.id}" if o.manual_invoice_id else f"{p.tx_number} · order #{o.id}"
                    out.append(_cand(tx, Target(order=o, label=label)))
    seen, rows = set(), []
    for c in sorted(out, key=lambda c: -c["score"]):
        if c["key"] in seen:
            continue
        seen.add(c["key"])
        rows.append(c)
    return rows[:limit]


def _cand(tx, t: Target, why: list | None = None) -> dict:
    why = list(why or [])
    score = 100 if "typed" in why else 0
    amt, inv = Decimal(tx.amount_toman or 0), t.amount
    if amt and inv == amt:
        why.append("same_amount"); score += 40
    elif amt and inv:
        score += max(0, 20 - int(abs(inv - amt) * 100 / inv))
    if t.agency is not None:
        ap = t.agency
        who, ref, at = ap.payer_username, ap.receipt_ref, ap.created_at
        status, ref_ok = ap.status, ref_match(tx, ap.receipt_ref)
        key, ref_label = f"ap:{ap.pk}", ap.number
    else:
        o, p = t.order, t.payment
        who = (o.user.name or o.user.username) if o.user_id else ""
        ref = p.receipt_ref if p else ""
        at = (p.confirmed_at if p and p.confirmed_at else o.created_at)
        status = o.status
        ref_ok = ref_match(tx, ref)
        key = f"order:{o.pk}"
        ref_label = o.manual_invoice.number if o.manual_invoice_id else (p.tx_number if p and p.number else f"#{o.id}")
    if ref_ok:
        why.append("same_reference"); score += 80
    if tx.payer_name and names_match(tx.payer_name, who):
        why.append("payer_name"); score += 25
    if at and abs((at - tx.occurred_at).total_seconds()) <= 6 * 3600:
        why.append("time"); score += 10
    return {"key": key, "ref": ref_label, "label": t.describe(), "kind": "agency" if t.agency is not None else "order",
            "amount": t.amount, "status": status, "paid": t.paid, "who": who, "at": at, "why": why, "score": score}


# --------------------------------------------------------------------------------------------- link / unlink
def _set_linked(tx, *, order=None, payment=None, agency=None, note: str) -> None:
    tx.status, tx.matched_order, tx.matched_payment, tx.match_note = BluStatus.LINKED, order, payment, note[:255]
    BluTransaction.objects.filter(pk=tx.pk).update(status=BluStatus.LINKED, matched_order=order, matched_payment=payment,
                                                   match_note=note[:255])
    if payment is not None and payment.blu_transaction_id is None:
        Payment.objects.filter(pk=payment.pk).update(blu_transaction=tx)
    if agency is not None and agency.blu_transaction_id is None:
        type(agency).objects.filter(pk=agency.pk).update(blu_transaction=tx)


def _link_only(tx, t: Target, *, staff=None, how: str) -> str:
    if t.agency is not None:
        _set_linked(tx, agency=t.agency, note=f"linked to existing agency payment {t.agency.number} ({how})")
        target = t.agency
    else:
        p = t.payment
        _set_linked(tx, order=t.order, payment=p,
                    note=f"linked to existing payment {p.tx_number if p else ''} · order #{t.order.id} ({how})")
        target = p or t.order
    write_audit(action="blu.linked", staff=staff if staff is not None else "system", target=target,
                detail={"blu_transaction": tx.id, "target": t.describe(), "how": how, "amount": str(tx.amount_toman),
                        "receipt": tx.receipt, "reference": tx.reference})
    return "linked"


@transaction.atomic
def link(tx_id: int, ref, staff, *, confirm: bool = False) -> dict:
    """Staff «اتصال». Returns {result: approved | linked, target, shortfall?}."""
    from apps.orders.models import OrderStatus

    from .services import _FULFILLABLE

    tx = BluTransaction.objects.select_for_update().filter(pk=tx_id).first()
    if tx is None:
        raise LinkError("deposit not found", "واریز پیدا نشد", "not_found", 404)
    if tx.status not in (BluStatus.UNMATCHED, BluStatus.DUPLICATE):
        raise LinkError(f"this deposit is already {tx.status}", "این واریز قبلاً به پرداختی وصل شده است", "not_unmatched", 409)
    t = resolve(ref)
    if t.agency is not None:
        type(t.agency).objects.select_for_update().filter(pk=t.agency.pk).first()
        t.agency.refresh_from_db()
    else:
        type(t.order).objects.select_for_update().filter(pk=t.order.pk).first()
        t.order.refresh_from_db()
    if t.paid:
        _link_only(tx, t, staff=staff, how=f"by {staff.username}")
        return {"result": "linked", "target": t.describe()}
    deposit, invoice = Decimal(tx.amount_toman or 0), t.amount
    if deposit <= 0:
        raise LinkError("this deposit has no whole-toman amount", "مبلغ این واریز تومان کامل نیست", "amount")
    if deposit != invoice and not confirm:
        short = invoice - deposit
        raise LinkError(
            f"the deposit ({deposit:,} T) differs from {t.describe()} ({invoice:,} T) — confirm to approve"
            + (f"; the shortfall {short:,} T is recorded" if short > 0 else ""),
            f"مبلغ واریز ({deposit:,} تومان) با {t.describe()} ({invoice:,} تومان) برابر نیست — برای تأیید، تأیید کنید"
            + (f"؛ کسری {short:,} تومان ثبت می‌شود" if short > 0 else ""),
            "needs_confirm", 409, deposit=str(deposit), invoice=str(invoice), shortfall=str(short) if short > 0 else None)
    if t.agency is not None:
        from apps.agency import billing

        billing.approve_payment(t.agency.pk, staff=staff, source="blu_auto", deposit=deposit, tx=tx)
        BluTransaction.objects.filter(pk=tx.pk).update(
            status=BluStatus.MATCHED, match_note=f"agency payment {t.agency.number} — attached by {staff.username}"[:255])
        write_audit(action="blu.attached_agency", staff=staff, target=t.agency,
                    detail={"blu_transaction": tx.id, "deposit": str(deposit), "invoice": str(invoice)})
        return {"result": "approved", "target": t.describe(),
                "shortfall": str(invoice - deposit) if deposit < invoice else None}
    if t.order.status not in _FULFILLABLE and t.order.status != OrderStatus.PENDING_PAYMENT:
        raise LinkError(f"order #{t.order.id} is {t.order.status}", f"سفارش #{t.order.id} در وضعیت {t.order.status} است",
                        "order_state", 409)
    from .matching import confirm_blu

    payment = confirm_blu(t.order, tx, staff=staff, staff_short=deposit < invoice)
    return {"result": "approved", "target": t.describe(), "payment": payment.tx_number,
            "shortfall": str(payment.shortfall) if payment.shortfall else None}


@transaction.atomic
def unlink(tx_id: int, staff) -> BluTransaction:
    """Undo a LINK-ONLY connection (Super Admin). An approval made with the deposit is undone by voiding the payment."""
    from apps.agency.models import AgencyPayment

    tx = BluTransaction.objects.select_for_update().filter(pk=tx_id).first()
    if tx is None:
        raise LinkError("deposit not found", "واریز پیدا نشد", "not_found", 404)
    if tx.status != BluStatus.LINKED:
        raise LinkError("only a deposit linked to an existing payment can be unlinked (an approval is undone by "
                        "deleting the transaction)",
                        "فقط واریزی که به پرداخت موجود متصل شده جدا می‌شود (تأیید با حذف تراکنش برمی‌گردد)", "not_linked", 409)
    before = {"order": tx.matched_order_id, "payment": tx.matched_payment_id, "note": tx.match_note}
    # only the links this connection made (a payment approved WITH a deposit keeps it — that is not link-only)
    Payment.objects.filter(blu_transaction=tx).exclude(method="blu_auto").update(blu_transaction=None)
    AgencyPayment.objects.filter(blu_transaction=tx).exclude(method="blu_auto").update(blu_transaction=None)
    note = f"unlinked by {staff.username} — review by hand"
    BluTransaction.objects.filter(pk=tx.pk).update(status=BluStatus.UNMATCHED, matched_order=None, matched_payment=None,
                                                   match_note=note)
    write_audit(action="blu.unlinked", staff=staff, target=tx, detail={"blu_transaction": tx.id, **before})
    tx.refresh_from_db()
    return tx


# --------------------------------------------------------------------------------------------- auto-link
def _unmatched():
    return BluTransaction.objects.select_for_update().filter(status=BluStatus.UNMATCHED, amount_toman__isnull=False)


def _pick(tx_qs, *, refs: list, amounts: list, at, name: str):
    """The one deposit for a payment: same tracking / reference number; else exactly one with the same amount within
    AUTO_WINDOW of `at` and (when both are known) the same payer name."""
    for raw in refs:
        r = normalize_ref(raw)
        if len(r) >= 6:
            for tx in tx_qs.filter(occurred_at__gte=at - timedelta(days=30), occurred_at__lte=at + timedelta(days=2)):
                if ref_match(tx, r):
                    return tx, "same_reference"
    amounts = [Decimal(a) for a in amounts if a]
    if not amounts:
        return None, ""
    found = [tx for tx in tx_qs.filter(amount_toman__in=amounts, occurred_at__gte=at - AUTO_WINDOW,
                                       occurred_at__lte=at + AUTO_WINDOW)
             if not (tx.payer_name and name) or names_match(tx.payer_name, name)]
    if len(found) == 1:
        return found[0], "same_amount_time" + ("_name" if found[0].payer_name and name else "")
    return None, ""


def auto_link_payment(payment_id: int) -> int | None:
    """A customer payment was approved by a route other than Blu (manual invoice, staff receipt, SMS…)."""
    with transaction.atomic():
        p = (Payment.objects.select_for_update().select_related("order", "order__user").filter(pk=payment_id).first())
        if p is None or p.status != PaymentStatus.APPROVED or p.voided_at or p.blu_transaction_id or p.order_id is None:
            return None
        if BluTransaction.objects.filter(matched_payment=p).exists():
            return None
        o = p.order
        at = p.confirmed_at or timezone.now()
        tx, how = _pick(_unmatched(), refs=[p.receipt_ref], amounts=[p.amount, o.amount_unique], at=at,
                        name=(o.user.name if o.user_id else "") or "")
        if tx is None:
            return None
        label = f"{o.manual_invoice.number} · order #{o.id}" if o.manual_invoice_id else f"order #{o.id}"
        _link_only(tx, Target(order=o, label=label), how=f"auto: {how}")
        log.info("Blu %s auto-linked to payment %s (%s)", tx.id, p.tx_number, how)
        return tx.id


def auto_link_agency_payment(ap_id: int) -> int | None:
    from apps.agency.models import AgencyPayment

    with transaction.atomic():
        ap = AgencyPayment.objects.select_for_update().filter(pk=ap_id).first()
        if ap is None or ap.status != "approved" or ap.blu_transaction_id:
            return None
        tx, how = _pick(_unmatched(), refs=[ap.receipt_ref], amounts=[ap.paid_amount, ap.amount_unique],
                        at=ap.confirmed_at or timezone.now(), name="")
        if tx is None:
            return None
        _link_only(tx, Target(agency=ap, label=f"{ap.number} · {ap.payer_username}"), how=f"auto: {how}")
        return tx.id


def backfill(*, dry_run: bool = False) -> list[dict]:
    """One pass over approved payments / agency payments without a deposit, newest first (last 60 days)."""
    from apps.agency.models import AgencyPayment

    since = timezone.now() - timedelta(days=60)
    done = []
    with transaction.atomic():
        pays = list(Payment.objects.live().filter(status=PaymentStatus.APPROVED, blu_transaction__isnull=True,
                                                  confirmed_at__gte=since).exclude(method="blu_auto")
                    .order_by("-confirmed_at").values_list("id", flat=True))
        for pid in pays:
            tx_id = auto_link_payment(pid)
            if tx_id:
                done.append({"blu": tx_id, "payment": Payment.objects.get(pk=pid).tx_number})
        for apid in list(AgencyPayment.objects.filter(status="approved", blu_transaction__isnull=True,
                                                      confirmed_at__gte=since).values_list("id", flat=True)):
            tx_id = auto_link_agency_payment(apid)
            if tx_id:
                done.append({"blu": tx_id, "agency_payment": AgencyPayment.objects.get(pk=apid).number})
        if dry_run:
            transaction.set_rollback(True)
    return done


def prefill_for(payment) -> dict | None:
    """v1.44.1: the Blu deposit that most likely belongs to a payment in the review queue, so staff get the
    receipt amount and tracking number filled in: the deposit linked to it, else an unmatched deposit linked
    to its order, else the ONE unmatched deposit within ± the rounded tolerance inside the order's window.
    Read-only — staff still save (and approve) themselves."""
    from apps.tenancy.context import store_id

    from .matching import _blu_window_ok
    from .models import BluStatus, BluTransaction
    from .rounded import config

    if store_id():
        return None                                   # v1.47: Blu deposits are ours only — never shown to a store
    order = payment.order
    tx = payment.blu_transaction if payment.blu_transaction_id else None
    if tx is None:
        tx = (BluTransaction.objects.filter(matched_order=order, status=BluStatus.UNMATCHED)
              .order_by("-occurred_at").first())
    if tx is None and order.amount_unique:
        t = config()["max_toman"]
        near = [x for x in BluTransaction.objects.filter(
                    status=BluStatus.UNMATCHED, matched_order__isnull=True, amount_toman__isnull=False,
                    amount_toman__gte=order.amount_unique - t, amount_toman__lte=order.amount_unique + t,
                    occurred_at__gte=order.created_at - timedelta(minutes=5)).order_by("occurred_at")[:5]
                if _blu_window_ok(order, x.occurred_at)]
        tx = near[0] if len(near) == 1 else None
    if tx is None or tx.amount_toman is None:
        return None
    return {"id": tx.id, "amount": tx.amount_toman, "tracking": tx.receipt or tx.reference,
            "receipt": tx.receipt, "reference": tx.reference, "occurred_at": tx.occurred_at,
            "payer_name": tx.payer_name}
