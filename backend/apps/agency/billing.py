"""Agency invoices, admin volume requests and agency payments (v1.34, docs/agency.md → "Invoices").

INVOICES — every agency charge issues one invoice for that admin (`issue_for_entry`):
  * a staff limit raise (quota_charge), a staff manual charge with GB (GB × price) or money,
  * an approved group-manager volume, an approved admin request (kind "request").
  The amount is the charge's amount = GB × the admin's price per GB of that day (ledger.py, the
  same price logic as Accounting). No price → NO charge: `NoPrice` («قیمت هر گیگ برای این ادمین
  تعریف نشده») is raised BEFORE anything changes on PasarGuard and staff get a Telegram with the
  admin and GB, so they can set the price and retry. Balances that existed before invoices:
  staff issue ONE «تسویه مانده قبلی» invoice per admin (`issue_settlement`, no ledger entry —
  the debt is already in the balance). Statuses: unpaid → pending (receipt / deposit under
  review) → paid, or voided (with its charge).

REQUESTS — an agency admin asks for GB in the /agency/ portal (`create_request`). It joins the
Approvals queue (VolumeRequest kind "request", «درخواست ادمین») and Telegram (Approve / Reject).
Approve (`managers.approve` → `approve_request`, staff with agency.manage + agency.accounting —
never a group manager): limit raised on PasarGuard at once from the last finite limit (v1.23.2),
quota charge + invoice. Reject: the reason is shown to the admin.

PAYMENTS — an admin pays one invoice (portal), a group manager one or several of its groups'
admins' invoices (panel), always the full amount (`create_payment`). Checkout like a customer:
bank card, unique amount (`amount_unique_lock`, shared pool with customer orders: each side
skips what the other holds; a deposit equal to both is never auto-approved), timer, optional
receipt. SMS / Blu deposits are matched exactly like customer orders (exact amount inside the
window, ±20 % / ×10 near miss → review, rounded-amount rule, duplicates). Approval
(`approve_payment`): invoices paid, a payment entry in each admin's ledger (balance down),
receipt kept, the payer notified in the portal. Agency payments live in their own table — never
in customer revenue, Transactions, Analytics or the customer payment queue.
"""
from __future__ import annotations

import logging
import random
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.models import write_audit

from .models import (AdminGroup, AgencyInvoice, AgencyNotice, AgencyPayment, AgencyPaymentItem, GroupManager,
                     LedgerEntry, PanelAdmin, VolumeRequest)

log = logging.getLogger("caspintunel")

GB = 1024 ** 3
D0 = Decimal(0)
NO_PRICE_FA = "قیمت هر گیگ برای این ادمین تعریف نشده"
NO_PRICE_EN = "No price per GB is set for this admin"
MAX_PENDING_REQUESTS = 5
CREATED_SKEW = timedelta(minutes=2)
NEAR_RATIO = Decimal("0.20")


class BillingError(Exception):
    STATUS = {"forbidden": 403, "not_found": 404, "no_price": 409, "conflict": 409, "busy": 409}

    def __init__(self, message: str, code: str = "invalid", *, fa: str = "", field: str | None = None, **extra):
        super().__init__(message)
        self.code, self.fa, self.field, self.extra = code, fa, field, extra

    @property
    def status(self) -> int:
        return self.STATUS.get(self.code, 400)

    def payload(self) -> dict:
        return {"detail": str(self), "detail_fa": self.fa or str(self), "code": self.code, "field": self.field,
                **self.extra}


class NoPrice(BillingError):
    def __init__(self, username: str, gb):
        super().__init__(f"{NO_PRICE_EN} ({username}) — set it in Agency → Accounting, then retry",
                         "no_price", fa=f"{NO_PRICE_FA} ({username})", field="price_per_gb",
                         admin=username, gb=str(gb))


def _gb_text(gb) -> str:
    try:
        return f"{Decimal(str(gb)).normalize():f}"
    except Exception:  # noqa: BLE001
        return str(gb)


def missing_price(username: str, gb, *, context: str = "") -> NoPrice:
    """Telegram to staff (agency.accounting) once an hour per admin, then the error to raise."""
    from apps.common.staff_alert import alert_staff

    try:
        alert_staff(f"💲 {NO_PRICE_FA}: ادمین {username} · {_gb_text(gb)} GB{f' · {context}' if context else ''}\n"
                    f"{NO_PRICE_EN}: {username}, {_gb_text(gb)} GB — set the price in Agency → Accounting, then retry.",
                    perm="agency.accounting", dedupe_key=f"agency:noprice:{username}", ttl=3600)
    except Exception as exc:  # noqa: BLE001
        log.warning("no-price alert failed: %s", exc)
    return NoPrice(username, gb)


def ensure_price(username: str, gb, day=None, *, context: str = ""):
    from . import ledger

    p = ledger.price_at(username, day)
    if p is None:
        raise missing_price(username, gb, context=context)
    return p


def group_of(username: str) -> AdminGroup | None:
    g = AdminGroup.get_group_for_owner(username)
    if g:
        return g
    for g in AdminGroup.objects.all():
        if username in g.get_all_usernames():
            return g
    return None


def _group_name(g) -> str:
    if g is None:
        return ""
    from .managers import group_title

    return group_title(g)


# ------------------------------------------------------------------ notices
def notice(*, admin: str = "", manager: GroupManager | None = None, kind: str, title: str, title_en: str,
           body: str = "", body_en: str = "") -> None:
    AgencyNotice.objects.create(admin_username=admin or "", manager=manager, kind=kind, title=title[:200],
                                title_en=title_en[:200], body=body, body_en=body_en)


def managers_of(username: str) -> list[GroupManager]:
    g = group_of(username)
    if g is None:
        return []
    return list(GroupManager.objects.filter(is_active=True, assignments__group=g).distinct())


def notice_admin_and_managers(username: str, **kw) -> None:
    notice(admin=username, **kw)
    for m in managers_of(username):
        notice(manager=m, **kw)


# ------------------------------------------------------------------ invoices
def _kind_for(entry: LedgerEntry, volume_request: VolumeRequest | None) -> str:
    if volume_request is not None:
        return AgencyInvoice.KIND_REQUEST
    return AgencyInvoice.KIND_QUOTA if entry.kind == LedgerEntry.KIND_QUOTA else AgencyInvoice.KIND_CHARGE


def issue_for_entry(entry: LedgerEntry | None, *, volume_request: VolumeRequest | None = None,
                    by: str = "") -> AgencyInvoice | None:
    """The invoice of one charge (called right after the ledger entry is written)."""
    if entry is None or entry.amount <= 0 or entry.kind not in (LedgerEntry.KIND_QUOTA, LedgerEntry.KIND_CHARGE):
        return None
    g = group_of(entry.admin_username)
    inv = AgencyInvoice.objects.create(
        admin_username=entry.admin_username, group=g, group_name=_group_name(g), kind=_kind_for(entry, volume_request),
        gb=entry.gb, price_per_gb=entry.price_per_gb, amount=entry.amount, ledger_entry=entry,
        volume_request=volume_request, note=(entry.note or "")[:255], created_by=(by or entry.created_by or "")[:150])
    transaction.on_commit(lambda: _issued(inv))
    return inv


def _issued(inv: AgencyInvoice) -> None:
    gb = f" · {_gb_text(inv.gb)} GB" if inv.gb else ""
    try:
        notice_admin_and_managers(
            inv.admin_username, kind="invoice_issued",
            title=f"فاکتور {inv.number} صادر شد", title_en=f"Invoice {inv.number} issued",
            body=f"{inv.admin_username}{gb} · {inv.amount:,} تومان", body_en=f"{inv.admin_username}{gb} · {inv.amount:,} T")
    except Exception as exc:  # noqa: BLE001
        log.warning("invoice notice failed: %s", exc)


def open_total(username: str) -> Decimal:
    from django.db.models import Sum

    return (AgencyInvoice.objects.filter(admin_username=username,
                                         status__in=(AgencyInvoice.UNPAID, AgencyInvoice.PENDING))
            .aggregate(s=Sum("amount"))["s"] or D0)


def settlement_quote(username: str) -> dict:
    from . import ledger

    bal = ledger.balances().get(username, D0)
    existing = AgencyInvoice.objects.filter(admin_username=username, kind=AgencyInvoice.KIND_SETTLEMENT) \
        .exclude(status=AgencyInvoice.VOIDED).first()
    amount = bal - open_total(username)
    return {"balance": bal, "open_invoices": open_total(username), "amount": max(D0, amount),
            "existing": existing.number if existing else None, "allowed": existing is None and amount > 0}


@transaction.atomic
def issue_settlement(username: str, *, by: str = "") -> AgencyInvoice:
    """«تسویه مانده قبلی»: the balance not covered by open invoices, once per admin."""
    if not PanelAdmin.objects.filter(username=username).exists():
        raise BillingError("unknown admin", "not_found")
    list(PanelAdmin.objects.select_for_update().filter(username=username))     # serialize per admin
    q = settlement_quote(username)
    if q["existing"]:
        raise BillingError(f"this admin already has a previous-balance invoice ({q['existing']})", "conflict",
                           fa=f"برای این ادمین فاکتور تسویهٔ مانده قبلی صادر شده است ({q['existing']})")
    if q["amount"] <= 0:
        raise BillingError("nothing to settle: the balance is covered by open invoices (or zero)", "invalid",
                           fa="مانده‌ای برای تسویه نیست")
    g = group_of(username)
    inv = AgencyInvoice.objects.create(admin_username=username, group=g, group_name=_group_name(g),
                                       kind=AgencyInvoice.KIND_SETTLEMENT, amount=q["amount"],
                                       note="previous balance (before invoices)", created_by=by[:150])
    transaction.on_commit(lambda: _issued(inv))
    return inv


@transaction.atomic
def void_invoice(invoice_id: int, *, reason: str, by: str = "") -> AgencyInvoice:
    from . import ledger

    inv = AgencyInvoice.objects.select_for_update().filter(pk=invoice_id).first()
    if inv is None:
        raise BillingError("invoice not found", "not_found")
    if inv.status != AgencyInvoice.UNPAID:
        raise BillingError(f"only an unpaid invoice can be voided (this one is {inv.status})", "conflict",
                           fa="فقط فاکتور پرداخت‌نشده باطل می‌شود")
    if not (reason or "").strip():
        raise BillingError("a reason is required", "invalid", field="reason")
    _cancel_open_payments([inv.id])
    inv.status, inv.voided_at, inv.void_reason = AgencyInvoice.VOIDED, timezone.now(), reason.strip()[:255]
    inv.save(update_fields=["status", "voided_at", "void_reason"])
    if inv.ledger_entry_id and not inv.ledger_entry.voided:
        ledger.void(inv.ledger_entry_id, f"invoice {inv.number} voided: {reason}", by=by, _from_invoice=True)
    return inv


def on_ledger_void(entry: LedgerEntry) -> None:
    """A voided charge takes its unpaid invoice with it."""
    for inv in AgencyInvoice.objects.select_for_update().filter(ledger_entry=entry, status=AgencyInvoice.UNPAID):
        _cancel_open_payments([inv.id])
        inv.status, inv.voided_at, inv.void_reason = AgencyInvoice.VOIDED, timezone.now(), "charge voided"
        inv.save(update_fields=["status", "voided_at", "void_reason"])


def invoice_row(inv: AgencyInvoice) -> dict:
    open_p = (AgencyPayment.objects.filter(items__invoice=inv, status__in=AgencyPayment.ACTIVE)
              .order_by("-id").values_list("id", "status").first())
    return {"id": inv.id, "number": inv.number, "admin": inv.admin_username, "group": inv.group_name,
            "group_id": inv.group_id, "kind": inv.kind, "gb": inv.gb, "price_per_gb": inv.price_per_gb,
            "amount": inv.amount, "status": inv.status, "note": inv.note, "created_at": inv.created_at,
            "paid_at": inv.paid_at, "voided_at": inv.voided_at, "void_reason": inv.void_reason,
            "request": inv.volume_request_id,
            "open_payment": {"id": open_p[0], "status": open_p[1]} if open_p else None}


def invoices_payload(usernames: list[str], status: str | None = None) -> dict:
    qs = AgencyInvoice.objects.filter(admin_username__in=usernames)
    if status and status != "all":
        qs = qs.filter(status=status)
    rows = [invoice_row(i) for i in qs[:500]]
    unpaid = AgencyInvoice.objects.filter(admin_username__in=usernames, status=AgencyInvoice.UNPAID)
    from django.db.models import Sum

    return {"results": rows, "unpaid_total": unpaid.aggregate(s=Sum("amount"))["s"] or D0,
            "unpaid_count": unpaid.count(),
            "pending_count": AgencyInvoice.objects.filter(admin_username__in=usernames,
                                                          status=AgencyInvoice.PENDING).count()}


# ------------------------------------------------------------------ admin requests (portal)
def quote(username: str, gb) -> dict:
    from . import ledger
    from .actions import base_limit

    gb = _positive(gb)
    p = ledger.price_at(username)
    a = PanelAdmin.objects.filter(username=username).first()
    base = base_limit(a) if a else 0
    return {"gb": gb, "price_per_gb": p.price_per_gb if p else None,
            "amount": (gb * p.price_per_gb).quantize(Decimal(1), rounding=ROUND_HALF_UP) if p else None,
            "missing_price": p is None, "missing_price_fa": NO_PRICE_FA if p is None else "",
            "current_limit_bytes": base, "new_limit_bytes": base + int(gb * GB)}


def _positive(gb) -> Decimal:
    try:
        v = Decimal(str(gb).strip().replace(",", ""))
    except Exception as exc:  # noqa: BLE001
        raise BillingError("enter the volume in GB", "invalid", fa="حجم را به گیگ وارد کنید", field="gb") from exc
    if v <= 0 or v > 1_000_000 or v != v.quantize(Decimal("0.01")):
        raise BillingError("the volume must be a positive number of GB (2 decimals max)", "invalid",
                           fa="حجم باید عددی مثبت (حداکثر دو رقم اعشار) باشد", field="gb")
    return v


def create_request(username: str, gb, note: str = "") -> VolumeRequest:
    from .actions import base_limit

    gb = _positive(gb)
    a = PanelAdmin.objects.filter(username=username).first()
    if a is None:
        raise BillingError("no agency account for this username", "not_found")
    ensure_price(username, gb, context="portal request")
    if VolumeRequest.objects.filter(kind="request", requested_by=username, status="pending").count() >= MAX_PENDING_REQUESTS:
        raise BillingError("you already have several requests waiting — wait for staff to answer", "conflict",
                           fa="چند درخواست در انتظار دارید — منتظر پاسخ بمانید")
    base = base_limit(a)
    g = group_of(username)
    r = VolumeRequest.objects.create(group=g, group_name=_group_name(g), manager=None, manager_username="",
                                     admin_username=username, kind="request", gb=gb, old_limit_bytes=base,
                                     new_limit_bytes=base + int(gb * GB), requested_by=username, note=(note or "")[:255])
    write_audit(action="agency.request.created", staff=f"agency:{username}", target=r,
                detail={"admin": username, "gb": str(gb), "group": r.group_name})
    cache.delete("agency:approvals:badge")

    def send():
        try:
            from . import notify

            notify.approval_requested(r)
        except Exception as exc:  # noqa: BLE001
            log.warning("agency request notification failed: %s", exc)
        _live("agency_request", request_id=r.id, admin=username)
    transaction.on_commit(send)
    return r


def approve_request(r: VolumeRequest, by, staff_label: str):
    """Inside managers.approve (row locked): PasarGuard first, then charge + invoice."""
    from urllib.parse import quote as q

    from . import ledger, limit_history
    from .actions import base_limit, gb_label
    from .admin_crud import AdminCrudError, get_admin
    from .managers import ManagerError, _client, _panel, _panel_err

    a = PanelAdmin.objects.select_for_update().filter(username=r.admin_username).first()
    if a is None:
        raise ManagerError("this admin is not on the panel any more", "not_found")
    ensure_price(r.admin_username, r.gb, context=f"request #{r.id}")
    try:
        live = get_admin(_panel(), r.admin_username)
    except AdminCrudError as exc:
        raise ManagerError(str(exc), exc.code) from exc
    live_limit = int(live.get("data_limit") or 0)
    # v1.23.2: an unlimited admin is charged / raised from its LAST finite limit
    base = live_limit if live_limit > 0 else base_limit(a)
    new = base + int(Decimal(r.gb) * GB)
    try:
        _client()._request("PUT", f"/api/admin/{q(r.admin_username, safe='')}", json={"data_limit": new})
    except Exception as exc:  # noqa: BLE001
        from apps.panel.exceptions import PanelError

        if isinstance(exc, PanelError):
            raise _panel_err(exc) from exc
        raise ManagerError(f"panel error: {exc}", "panel_error") from exc
    a.admin_limit_bytes, a.has_data_limit, a.last_limit_bytes = new, True, new
    a.admin_remaining = max(0, new - (a.admin_used_bytes or 0))
    a.save(update_fields=["admin_limit_bytes", "has_data_limit", "last_limit_bytes", "admin_remaining"])
    e = ledger.record_quota_charge(r.admin_username, base, new, by=staff_label,
                                   note=f"approved admin request #{r.id}", invoice=False)
    h = limit_history.record(r.admin_username, live_limit, new, action="add", source="panel", by=staff_label,
                             note=f"admin request #{r.id}: {gb_label(base)} → {gb_label(new)}", ledger_entry=e)
    r.old_limit_bytes, r.new_limit_bytes, r.limit_change = base, new, h
    inv = issue_for_entry(e, volume_request=r, by=staff_label)
    transaction.on_commit(lambda: notice(
        admin=r.admin_username, kind="request_approved",
        title=f"درخواست شارژ {_gb_text(r.gb)} گیگ تأیید شد", title_en=f"Your {_gb_text(r.gb)} GB request was approved",
        body=f"سقف جدید: {gb_label(new)}" + (f" · فاکتور {inv.number}: {inv.amount:,} تومان" if inv else ""),
        body_en=f"New limit: {gb_label(new)}" + (f" · invoice {inv.number}: {inv.amount:,} T" if inv else "")))
    return e


def reject_request(r: VolumeRequest, reason: str) -> None:
    reason = (reason or "").strip()[:255]
    transaction.on_commit(lambda: notice(
        admin=r.admin_username, kind="request_rejected",
        title=f"درخواست شارژ {_gb_text(r.gb)} گیگ رد شد", title_en=f"Your {_gb_text(r.gb)} GB request was rejected",
        body=f"دلیل: {reason}" if reason else "", body_en=f"Reason: {reason}" if reason else ""))


# ------------------------------------------------------------------ payments
def _reservation_deadline():
    from apps.settings_app.utils import get_setting

    return timezone.now() + timedelta(minutes=int(get_setting("unique_amount_reservation_minutes", 30)))


def _surcharges() -> list[int]:
    from apps.settings_app.utils import get_setting

    lo = int(get_setting("unique_amount_min", 200))
    hi = int(get_setting("unique_amount_max", 1500))
    vals = list(range(lo, hi + 1))
    random.shuffle(vals)
    return vals


def customer_locked(amount) -> bool:
    from apps.orders.models import Order

    return Order.objects.filter(amount_unique_lock=amount).exists()


def agency_locked_amounts() -> set:
    """For the customer order picker: amounts an agency payment holds right now."""
    return set(AgencyPayment.objects.filter(amount_unique_lock__isnull=False).values_list("amount_unique_lock", flat=True))


def _live(event: str, **data) -> None:
    try:
        from apps.notifications.live import push_payments_event

        push_payments_event(event, **data)
    except Exception as exc:  # noqa: BLE001
        log.warning("agency live event failed: %s", exc)


def _cancel_open_payments(invoice_ids: list[int]) -> None:
    for p in AgencyPayment.objects.select_for_update().filter(items__invoice_id__in=invoice_ids,
                                                              status=AgencyPayment.PENDING_PAYMENT).distinct():
        p.status = AgencyPayment.CANCELLED
        p.sync_unique_lock()
        p.save(update_fields=["status", "amount_unique_lock", "updated_at"])


@transaction.atomic
def create_payment(invoice_ids: list[int], *, payer_kind: str, payer_username: str,
                   allowed_admins: list[str], manager: GroupManager | None = None) -> AgencyPayment:
    """Pay these invoices (full amounts). `allowed_admins` = whose invoices this payer may pay."""
    from apps.payments_sms.services import default_bank_card

    ids = sorted({int(i) for i in invoice_ids or []})
    if not ids:
        raise BillingError("choose at least one invoice", "invalid", fa="دست‌کم یک فاکتور انتخاب کنید")
    if payer_kind == "admin" and len(ids) != 1:
        raise BillingError("pay one invoice at a time", "invalid", fa="هر بار یک فاکتور را پرداخت کنید")
    invs = list(AgencyInvoice.objects.select_for_update().filter(pk__in=ids))
    if len(invs) != len(ids) or any(i.admin_username not in allowed_admins for i in invs):
        raise BillingError("not your invoice", "forbidden", fa="این فاکتور متعلق به شما نیست")
    bad = [i.number for i in invs if i.status != AgencyInvoice.UNPAID]
    if bad:
        raise BillingError(f"already paid, voided or under review: {', '.join(bad)}", "conflict",
                           fa=f"این فاکتورها پرداخت‌شده، باطل یا در حال بررسی‌اند: {', '.join(bad)}")
    _cancel_open_payments(ids)                     # a new checkout replaces an unfinished one
    total = sum((i.amount for i in invs), D0)
    p = AgencyPayment(payer_kind=payer_kind, payer_username=payer_username, manager=manager, amount=total,
                      unique_expire_at=_reservation_deadline(), bank_card=default_bank_card())
    for extra in _surcharges():
        cand = total + Decimal(extra)
        if customer_locked(cand):                  # one pool with customer orders
            continue
        p.amount_unique = p.amount_unique_lock = cand
        try:
            with transaction.atomic():
                p.save()
            break
        except IntegrityError:
            continue
    else:
        raise BillingError("could not reserve a unique amount right now — try again", "busy",
                           fa="الان مبلغ یکتا رزرو نشد — دوباره تلاش کنید")
    AgencyPaymentItem.objects.bulk_create([AgencyPaymentItem(payment=p, invoice=i, amount=i.amount) for i in invs])
    write_audit(action="agency.payment.created", staff=f"agency:{payer_username}", target=p,
                detail={"invoices": [i.number for i in invs], "amount": str(total), "unique": str(p.amount_unique),
                        "payer": payer_kind})
    return p


def payment_row(p: AgencyPayment, *, staff: bool = False) -> dict:
    from apps.payments_sms.models import BankCard

    items = list(p.items.select_related("invoice"))
    cards = BankCard.objects.filter(is_active=True).order_by("sort_order", "id")
    row = {"id": p.id, "number": p.number, "status": p.status, "payer_kind": p.payer_kind, "payer": p.payer_username,
           "amount": p.amount, "amount_unique": p.amount_unique, "unique_expire_at": p.unique_expire_at,
           "paid_amount": p.paid_amount, "shortfall": p.shortfall, "auto_rule": p.auto_rule,
           "method": p.method, "reject_reason": p.reject_reason, "created_at": p.created_at,
           "confirmed_at": p.confirmed_at, "has_receipt": bool(p.receipt_image),
           "invoices": [{"id": it.invoice_id, "number": it.invoice.number, "admin": it.invoice.admin_username,
                         "group": it.invoice.group_name, "amount": it.amount, "kind": it.invoice.kind,
                         "gb": it.invoice.gb} for it in items],
           "admins": sorted({it.invoice.admin_username for it in items}),
           "cards": [{"id": c.id, "card_number": c.card_number, "holder_name": c.holder_name, "bank_name": c.bank_name}
                     for c in cards]}
    if staff:
        from apps.payments_sms.checks import normalize_ref  # noqa: F401  (same normalization as customers)

        row.update({"receipt_url": f"/api/v1/admin/agency/payments/{p.id}/receipt/" if p.receipt_image else None,
                    "receipt_ref": p.receipt_ref, "mismatch_kind": p.mismatch_kind, "mismatch_amount": p.mismatch_amount,
                    "auto_reason": p.auto_reason or {}, "confirmed_by": p.confirmed_by,
                    "confirmed_by_staff": p.confirmed_by_staff.username if p.confirmed_by_staff_id else None,
                    "sms_message": p.sms_message_id, "blu_transaction": p.blu_transaction_id,
                    "warnings": warnings(p)})
    return row


@transaction.atomic
def submit_receipt(payment_id: int, *, image, receipt_ref: str, payer_check) -> AgencyPayment:
    from apps.payments_sms.checks import image_sha256, normalize_ref

    p = AgencyPayment.objects.select_for_update().filter(pk=payment_id).first()
    if p is None or not payer_check(p):
        raise BillingError("payment not found", "not_found")
    if p.status not in (AgencyPayment.PENDING_PAYMENT, AgencyPayment.PENDING_REVIEW):
        raise BillingError(f"this payment is {p.status}", "conflict", fa="این پرداخت دیگر باز نیست")
    if p.status == AgencyPayment.PENDING_PAYMENT and p.unique_expire_at < timezone.now():
        raise BillingError("the reservation has expired — start the payment again", "conflict",
                           fa="مهلت پرداخت تمام شده — دوباره پرداخت را شروع کنید")
    p.receipt_image = image
    p.receipt_sha256 = image_sha256(image)
    p.receipt_ref = normalize_ref(receipt_ref)
    p.receipt_uploaded_at = timezone.now()
    p.status = AgencyPayment.PENDING_REVIEW
    p.sync_unique_lock()
    p.save()
    AgencyInvoice.objects.filter(payment_items__payment=p, status=AgencyInvoice.UNPAID).update(status=AgencyInvoice.PENDING)
    write_audit(action="agency.payment.receipt", staff=f"agency:{p.payer_username}", target=p,
                detail={"payment": p.number})

    def after():
        from apps.common.staff_alert import alert_staff

        alert_staff(f"🧾 رسید واریز نماینده {p.number} — {p.payer_username} · {p.amount_unique:,} تومان — در «واریزهای نمایندگان» بررسی کنید.\n"
                    f"Agency receipt {p.number} — {p.payer_username}, {p.amount_unique:,} T.",
                    perm="agency.payments", dedupe_key=f"agency:receipt:{p.id}:{p.receipt_sha256[:8]}", ttl=3600,
                    push={"title": f"رسید نماینده · Agency receipt {p.number}", "body": p.payer_username,
                          "url": "/agency/ledger/payments", "tag": f"agency-pay:{p.id}"})
        _live("agency_receipt", payment_id=p.id, payer=p.payer_username)
        try:
            retry_rounded(p.id)
        except Exception as exc:  # noqa: BLE001
            log.warning("agency rounded retry failed: %s", exc)
    transaction.on_commit(after)
    return p


@transaction.atomic
def cancel_payment(payment_id: int, *, payer_check) -> AgencyPayment:
    p = AgencyPayment.objects.select_for_update().filter(pk=payment_id).first()
    if p is None or not payer_check(p):
        raise BillingError("payment not found", "not_found")
    if p.status != AgencyPayment.PENDING_PAYMENT:
        raise BillingError("only an unfinished payment can be cancelled", "conflict", fa="این پرداخت قابل لغو نیست")
    p.status = AgencyPayment.CANCELLED
    p.sync_unique_lock()
    p.save(update_fields=["status", "amount_unique_lock", "updated_at"])
    return p


def _ledger_payments(p: AgencyPayment, paid: Decimal, by: str) -> None:
    """One payment entry per admin (balance down). A rounded shortfall stays owed."""
    per: dict[str, Decimal] = {}
    for it in p.items.select_related("invoice"):
        per[it.invoice.admin_username] = per.get(it.invoice.admin_username, D0) + it.amount
    short = max(D0, p.amount - paid)
    names = sorted(per)
    for n in reversed(names):                       # take the shortfall off the last admins first
        cut = min(short, per[n])
        per[n] -= cut
        short -= cut
    for n in names:
        if per[n] > 0:
            LedgerEntry.objects.create(admin_username=n, kind=LedgerEntry.KIND_PAYMENT, amount=per[n],
                                       date=timezone.localdate(), method="card",
                                       note=f"agency payment {p.number}"[:255], created_by=by[:150])


@transaction.atomic
def approve_payment(payment_id: int, *, staff=None, source: str = "manual", deposit=None, sms=None, tx=None,
                    rounded: dict | None = None) -> AgencyPayment:
    """source: manual (staff) | sms_auto | blu_auto. `deposit` = what arrived (tomans)."""
    p = AgencyPayment.objects.select_for_update().filter(pk=payment_id).first()
    if p is None:
        raise BillingError("payment not found", "not_found")
    if p.status == AgencyPayment.APPROVED:
        return p
    if p.status not in (AgencyPayment.PENDING_PAYMENT, AgencyPayment.PENDING_REVIEW, AgencyPayment.EXPIRED,
                        AgencyPayment.REJECTED):
        raise BillingError(f"this payment is {p.status}", "conflict")
    # what arrived: the deposit, or (staff approval) the near-miss deposit if there was one, else the unique amount
    if deposit is not None:
        paid = Decimal(deposit)
    elif p.mismatch_kind and p.mismatch_amount is not None:
        paid = p.mismatch_amount
    else:
        paid = p.amount_unique
    # the few hundred tomans that made the amount unique are not debt: the invoices get at most their total
    covered = min(paid, p.amount)
    by = getattr(staff, "username", "") or "system"
    p.status = AgencyPayment.APPROVED
    p.sync_unique_lock()
    p.paid_amount = paid
    p.method = source
    p.confirmed_by = "admin" if staff is not None else "system"
    p.confirmed_by_staff = staff
    p.confirmed_at = timezone.now()
    p.reject_reason = ""
    if sms is not None:
        p.sms_message = sms
    if tx is not None:
        p.blu_transaction = tx
    if rounded:
        p.auto_rule, p.auto_reason = "rounded", rounded
    p.shortfall = (p.amount - covered) if covered < p.amount else None
    p.save()
    _ledger_payments(p, covered, by)
    now = timezone.now()
    AgencyInvoice.objects.filter(payment_items__payment=p).exclude(status=AgencyInvoice.VOIDED) \
        .update(status=AgencyInvoice.PAID, paid_at=now)
    write_audit(action="agency.payment.approved", staff=staff if staff is not None else "system", target=p,
                detail={"payment": p.number, "source": source, "paid": str(paid), "amount": str(p.amount),
                        "shortfall": str(p.shortfall) if p.shortfall else None,
                        "invoices": [it.invoice.number for it in p.items.select_related("invoice")]})

    def after():
        _paid_notices(p)
        _live("agency_approved", payment_id=p.id, payer=p.payer_username, source=source)
        if staff is None:
            from apps.common.staff_alert import alert_staff

            label = "مبلغ گرد شده" if rounded else ("بلو" if source == "blu_auto" else "پیامک")
            alert_staff(f"✅ واریز نماینده {p.number} خودکار تأیید شد ({label}) — {p.payer_username} · {paid:,} تومان.\n"
                        f"Agency payment {p.number} auto-approved ({source}) — {p.payer_username}, {paid:,} T.",
                        perm="agency.payments", dedupe_key=f"agency:auto:{p.id}", ttl=86400,
                        push={"title": f"واریز نماینده تأیید شد · {p.number}", "body": p.payer_username,
                              "url": "/agency/ledger/payments", "tag": f"agency-pay:{p.id}"})
    transaction.on_commit(after)
    return p


def _paid_notices(p: AgencyPayment) -> None:
    title, title_en = f"پرداخت {p.number} تأیید شد", f"Payment {p.number} approved"
    nums = ", ".join(it.invoice.number for it in p.items.select_related("invoice"))
    body, body_en = f"فاکتورها: {nums} · {p.paid_amount:,} تومان", f"Invoices: {nums} · {p.paid_amount:,} T"
    if p.payer_kind == "manager" and p.manager_id:
        notice(manager=p.manager, kind="payment_approved", title=title, title_en=title_en, body=body, body_en=body_en)
    else:
        notice(admin=p.payer_username, kind="payment_approved", title=title, title_en=title_en, body=body, body_en=body_en)


@transaction.atomic
def reject_payment(payment_id: int, *, staff, reason: str) -> AgencyPayment:
    p = AgencyPayment.objects.select_for_update().filter(pk=payment_id).first()
    if p is None:
        raise BillingError("payment not found", "not_found")
    if p.status not in (AgencyPayment.PENDING_PAYMENT, AgencyPayment.PENDING_REVIEW, AgencyPayment.EXPIRED):
        raise BillingError(f"this payment is {p.status}", "conflict")
    reason = (reason or "").strip()
    if len(reason) < 2:
        raise BillingError("a reason is required (the payer sees it)", "invalid", field="reason")
    p.status, p.reject_reason = AgencyPayment.REJECTED, reason[:255]
    p.sync_unique_lock()
    p.confirmed_by_staff, p.confirmed_at = staff, timezone.now()
    p.save()
    AgencyInvoice.objects.filter(payment_items__payment=p, status=AgencyInvoice.PENDING).update(status=AgencyInvoice.UNPAID)
    write_audit(action="agency.payment.rejected", staff=staff, target=p, detail={"payment": p.number, "reason": p.reject_reason})

    def after():
        kw = dict(kind="payment_rejected", title=f"پرداخت {p.number} رد شد", title_en=f"Payment {p.number} rejected",
                  body=f"دلیل: {p.reject_reason}", body_en=f"Reason: {p.reject_reason}")
        if p.payer_kind == "manager" and p.manager_id:
            notice(manager=p.manager, **kw)
        else:
            notice(admin=p.payer_username, **kw)
        _live("agency_rejected", payment_id=p.id)
    transaction.on_commit(after)
    return p


def expire_stale() -> int:
    """Unfinished checkouts past their reservation release the unique amount (invoices stay unpaid)."""
    n = 0
    for p in AgencyPayment.objects.select_for_update().filter(status=AgencyPayment.PENDING_PAYMENT,
                                                              unique_expire_at__lt=timezone.now()):
        p.status = AgencyPayment.EXPIRED
        p.sync_unique_lock()
        p.save(update_fields=["status", "amount_unique_lock", "updated_at"])
        n += 1
    return n


def badge() -> int:
    return AgencyPayment.objects.filter(status=AgencyPayment.PENDING_REVIEW).count()


def warnings(p: AgencyPayment) -> list[dict]:
    """Duplicate receipt image / bank document number — against agency AND customer payments."""
    from apps.payments_sms.models import Payment

    out = []
    if p.receipt_sha256:
        same = list(AgencyPayment.objects.filter(receipt_sha256=p.receipt_sha256).exclude(pk=p.pk).values_list("id", flat=True)[:5])
        cust = list(Payment.objects.filter(receipt_sha256=p.receipt_sha256).values_list("id", flat=True)[:5])
        if same or cust:
            out.append({"kind": "duplicate_image", "agency_payments": same, "payments": cust})
    if p.receipt_ref:
        same = list(AgencyPayment.objects.filter(receipt_ref=p.receipt_ref).exclude(pk=p.pk).values_list("id", flat=True)[:5])
        cust = list(Payment.objects.filter(receipt_ref=p.receipt_ref).values_list("id", flat=True)[:5])
        if same or cust:
            out.append({"kind": "duplicate_ref", "agency_payments": same, "payments": cust})
    if p.mismatch_kind:
        out.append({"kind": "amount_mismatch", "deposit": str(p.mismatch_amount), "expected": str(p.amount_unique),
                    "direction": p.mismatch_kind})
    return out


# ------------------------------------------------------------------ SMS / Blu matching
def _grace() -> timedelta:
    from apps.payments_sms.blu import late_grace_minutes

    return timedelta(minutes=late_grace_minutes()[0])


def open_at(at):
    """Agency payments that could be paid by a deposit made at `at`: still open (waiting for the
    transfer / under review / expired since) and `at` inside created − 2 min … reservation end + grace."""
    return AgencyPayment.objects.filter(
        status__in=(AgencyPayment.PENDING_PAYMENT, AgencyPayment.PENDING_REVIEW, AgencyPayment.EXPIRED),
        created_at__lte=at + CREATED_SKEW, unique_expire_at__gte=at - _grace())


def exact(amount, at) -> AgencyPayment | None:
    if amount is None:
        return None
    return open_at(at).filter(amount_unique=Decimal(amount)).order_by("created_at").first()


def paid_duplicate(amount, at) -> AgencyPayment | None:
    if amount is None:
        return None
    return AgencyPayment.objects.filter(status=AgencyPayment.APPROVED, amount_unique=Decimal(amount),
                                        created_at__lte=at + CREATED_SKEW,
                                        unique_expire_at__gte=at - _grace()).order_by("-confirmed_at").first()


def near(amount, at) -> AgencyPayment | None:
    """±20 % of an open agency payment (or ×10 / ÷10) — never approved, flagged for review."""
    if amount is None or Decimal(amount) <= 0:
        return None
    t = Decimal(amount)
    unit = [v for v in (t * 10, t / 10) if v == v.to_integral_value()]
    hit = open_at(at).filter(amount_unique__in=unit).order_by("-created_at").first() if unit else None
    if hit:
        return hit
    best = None
    for p in open_at(at).filter(amount_unique__gte=(t / (1 + NEAR_RATIO)).to_integral_value() - 1,
                                amount_unique__lte=(t / (1 - NEAR_RATIO)).to_integral_value() + 1):
        inv = Decimal(p.amount_unique)
        if inv == t or abs(t - inv) > inv * NEAR_RATIO:
            continue
        if best is None or abs(t - inv) < abs(t - Decimal(best.amount_unique)):
            best = p
    return best


def flag_mismatch(p: AgencyPayment, amount, *, sms=None, tx=None) -> str:
    from apps.common.staff_alert import alert_staff

    p = AgencyPayment.objects.select_for_update().get(pk=p.pk)
    kind = "less" if Decimal(amount) < p.amount_unique else "more"
    p.mismatch_kind, p.mismatch_amount = kind, Decimal(amount)
    if sms is not None:
        p.sms_message = sms
    if tx is not None:
        p.blu_transaction = tx
    if p.status in (AgencyPayment.PENDING_PAYMENT, AgencyPayment.EXPIRED):
        p.status = AgencyPayment.PENDING_REVIEW
    p.sync_unique_lock()
    p.save()
    AgencyInvoice.objects.filter(payment_items__payment=p, status=AgencyInvoice.UNPAID).update(status=AgencyInvoice.PENDING)
    write_audit(action="agency.payment.amount_mismatch", target=p,
                detail={"payment": p.number, "kind": kind, "deposit": str(amount), "expected": str(p.amount_unique),
                        "sms": getattr(sms, "id", None), "blu": getattr(tx, "id", None)})
    fa = "کمتر" if kind == "less" else "بیشتر"
    transaction.on_commit(lambda: alert_staff(
        f"⚠️ مبلغ نامطابق (نماینده): واریز {Decimal(amount):,} تومان، {fa} از {p.number} ({p.amount_unique:,} تومان، {p.payer_username}). "
        f"در «واریزهای نمایندگان» بررسی کنید.\nAgency amount mismatch: deposit {Decimal(amount):,} T vs {p.number} "
        f"({p.amount_unique:,} T).", perm="agency.payments", dedupe_key=f"agency:mismatch:{p.id}:{amount}",
        push={"title": f"مبلغ نامطابق نماینده · {p.number}", "body": p.payer_username,
              "url": "/agency/ledger/payments", "tag": f"agency-pay:{p.id}"}))
    _live("agency_mismatch", payment_id=p.id, kind=kind)
    return kind


def has_receipt(p: AgencyPayment) -> bool:
    return bool(p.receipt_image)


def known_card(p: AgencyPayment, last4: str, exclude_tx: int | None = None) -> bool:
    """The payer card paid one of this payer's agency payments before."""
    from apps.payments_sms.models import BluTransaction

    if not last4 or len(last4) != 4:
        return False
    qs = BluTransaction.objects.filter(payer_last4=last4, agency_payments__status=AgencyPayment.APPROVED,
                                       agency_payments__payer_username=p.payer_username)
    if exclude_tx:
        qs = qs.exclude(pk=exclude_tx)
    return qs.exists()


def rounded_candidates(deposit: Decimal, at, cfg: dict, tolerance) -> list[AgencyPayment]:
    import math

    p_ = cfg["max_percent"] / 100
    hi = deposit + cfg["max_toman"]
    if p_ < 1:
        hi = max(hi, deposit / (1 - p_))
    out = []
    for p in open_at(at).filter(amount_unique__gt=deposit, amount_unique__lte=math.ceil(hi) + 1).order_by("created_at")[:20]:
        inv = Decimal(p.amount_unique)
        if deposit < inv and inv - deposit <= tolerance(inv, cfg):
            out.append(p)
    return out


def match_deposit(amount, at, *, sms=None, tx=None) -> tuple[str, AgencyPayment | None]:
    """Exact agency match for a deposit no customer order took: ("approved" | "duplicate" | "", payment)."""
    if amount is None:
        return "", None
    p = exact(amount, at)
    if p is not None:
        source = "blu_auto" if tx is not None else "sms_auto"
        p = approve_payment(p.id, source=source, deposit=Decimal(amount), sms=sms, tx=tx)
        if tx is not None:
            _mark_tx(tx, p)
        return "approved", p
    dup = paid_duplicate(amount, at)
    if dup is not None:
        return "duplicate", dup
    return "", None


def hold_ambiguous(p: AgencyPayment, amount, *, sms=None, tx=None) -> None:
    """The deposit equals a customer order AND this agency payment (should never happen — the
    pickers skip each other's amounts): nobody is auto-approved, staff decide."""
    p = AgencyPayment.objects.select_for_update().get(pk=p.pk)
    if sms is not None:
        p.sms_message = sms
    if tx is not None:
        p.blu_transaction = tx
    p.status = AgencyPayment.PENDING_REVIEW
    p.auto_reason = {"why_not": "ambiguous_customer_order", "deposit": str(amount)}
    p.sync_unique_lock()
    p.save()
    AgencyInvoice.objects.filter(payment_items__payment=p, status=AgencyInvoice.UNPAID).update(status=AgencyInvoice.PENDING)
    _live("agency_mismatch", payment_id=p.id, kind="ambiguous")


def retry_rounded(payment_id: int) -> str:
    """A receipt arrived: a deposit linked to this payment as LESS may now qualify (rounded.py)."""
    from apps.payments_sms import rounded
    from apps.payments_sms.models import BluStatus, BluTransaction

    p = AgencyPayment.objects.filter(pk=payment_id).first()
    if p is None or p.mismatch_kind != "less" or p.status != AgencyPayment.PENDING_REVIEW:
        return "no change"
    tx = p.blu_transaction
    if tx is not None and tx.status == BluStatus.UNMATCHED:
        with transaction.atomic():
            tx = BluTransaction.objects.select_for_update().get(pk=tx.pk)
            d = rounded.evaluate(tx.amount_toman, tx.occurred_at, source="blu", payer_last4=tx.payer_last4, tx_id=tx.pk)
            if d is not None and d.approve and isinstance(d.order, AgencyPayment) and d.order.pk == p.pk:
                approve_payment(p.id, source="blu_auto", deposit=tx.amount_toman, tx=tx, rounded=d.reason)
                _mark_tx(tx, p, rounded=True)
                return "approved by blu"
    msg = p.sms_message
    if msg is not None and msg.parsed_amount is not None:
        d = rounded.evaluate(msg.parsed_amount, msg.received_at, source="sms")
        if d is not None and d.approve and isinstance(d.order, AgencyPayment) and d.order.pk == p.pk:
            approve_payment(p.id, source="sms_auto", deposit=msg.parsed_amount, sms=msg, rounded=d.reason)
            return "approved by sms"
    return "no change"


def _mark_tx(tx, p: AgencyPayment, *, rounded: bool = False) -> None:
    from apps.payments_sms.models import BluStatus, BluTransaction

    note = f"agency payment {p.number} ({p.payer_username}) — " + ("rounded amount, auto-approved" if rounded else "auto-approved")
    BluTransaction.objects.filter(pk=tx.pk).update(status=BluStatus.MATCHED, match_note=note[:255])
