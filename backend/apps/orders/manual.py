"""v1.38 «فاکتور دستی» — staff invoices for a customer (docs/flows.md → "Manual invoice").

Mode A «قبلاً پرداخت شده» (`create_paid`): an Order + Payment are written and approved through
`payments_sms.services.approve_payment` with `confirmed_at` = the entered payment date/time, so revenue,
Accounting and Analytics count it on that day; confirmed_by = the staff member. Method card-to-card
(CARD_MANUAL, optional bank card) / cash / other; receipt image, tracking number → the usual duplicate
checks. Optional service action (default off): new service, renew or add volume on PasarGuard — the same
fulfilment as a paid order (`mark_paid_and_fulfill`). Without one, the order is completed as is.

Mode B «صدور فاکتور برای پرداخت» (`issue` → `pay`): the customer sees the open invoice in the site,
Mini App and bot and presses «پرداخت»; that creates a normal Order with the invoice amount (unique amount,
card, timer, receipt, SMS / Blu auto-confirm). When that order is paid, the invoice becomes paid
(`on_order_paid`) and the chosen service action runs.

Every order of a manual invoice carries `Order.manual_invoice` → the «دستی» tag everywhere.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.common.models import write_audit

from .models import ManualInvoice as MI
from .models import Order, OrderStatus, OrderType

log = logging.getLogger("caspintunel")
ORDER_TYPE = {MI.ACT_NONE: OrderType.MANUAL, MI.ACT_NEW: OrderType.NEW, MI.ACT_RENEW: OrderType.RENEW,
              MI.ACT_ADDON: OrderType.ADDON_VOLUME}
METHODS = {"card": "card_manual", "cash": "cash", "other": "other"}


class ManualInvoiceError(ValueError):
    def __init__(self, message: str, field: str | None = None, fa: str = ""):
        super().__init__(message)
        self.field, self.fa = field, fa or message


def _int_or_none(v, field):
    if v in (None, ""):
        return None
    try:
        n = int(str(v).strip())
    except ValueError:
        raise ManualInvoiceError(f"{field} must be a whole number", field, "باید عدد صحیح باشد")
    if n < 0:
        raise ManualInvoiceError(f"{field} must be positive", field, "باید مثبت باشد")
    return n


def clean_item(user, data: dict) -> dict:
    """Item + amount + service action, shared by both modes."""
    from apps.panel.models import Service
    from apps.plans.models import Plan, PlanType

    plan = None
    if data.get("plan"):
        plan = Plan.objects.filter(pk=data["plan"]).select_related("panel").first()
        if plan is None:
            raise ManualInvoiceError("plan not found", "plan", "پلن پیدا نشد")
    # Latin digits everywhere (CLAUDE.md): Persian / Arabic digits typed by staff are normalized on input
    title = str(data.get("title") or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")).strip()[:120]
    if plan is None and not title:
        raise ManualInvoiceError("choose a plan or enter a title", "title", "یک پلن انتخاب کنید یا عنوان بنویسید")
    try:
        amount = Decimal(str(data.get("amount") or "").replace(",", "").strip())
    except InvalidOperation:
        raise ManualInvoiceError("amount must be a number", "amount", "مبلغ باید عدد باشد")
    if amount <= 0 or amount != amount.to_integral_value():
        raise ManualInvoiceError("amount must be a positive whole number of tomans", "amount", "مبلغ باید عدد مثبت (تومان) باشد")
    action = data.get("service_action") or MI.ACT_NONE
    if action not in dict(MI.ACTIONS):
        raise ManualInvoiceError("unknown service action", "service_action")
    out = {"plan": plan, "title": title, "volume_gb": _int_or_none(data.get("volume_gb"), "volume_gb"),
           "days": _int_or_none(data.get("days"), "days"), "amount": amount, "service_action": action,
           "service": None, "account_name": "", "note": str(data.get("note") or "").strip()[:2000]}
    if action == MI.ACT_NONE:
        return out
    if plan is None:
        raise ManualInvoiceError("a service action needs a plan (its volume / days / panel)", "plan",
                                 "برای اعمال روی سرویس یک پلن انتخاب کنید")
    if action == MI.ACT_NEW:
        name = str(data.get("account_name") or "").strip()
        if not name:
            raise ManualInvoiceError("account name is required for a new service", "account_name", "نام اکانت را وارد کنید")
        from .services import OrderError, check_account_name

        try:
            check_account_name(plan.panel, name)
        except OrderError as exc:
            raise ManualInvoiceError(str(exc), "account_name")
        except Exception as exc:  # noqa: BLE001 — PanelNameTaken etc.
            raise ManualInvoiceError(f"this account name is taken: {exc}", "account_name", "این نام اکانت گرفته شده است")
        out["account_name"] = name
    else:
        svc = Service.objects.filter(pk=data.get("service") or 0, user=user).first()
        if svc is None:
            raise ManualInvoiceError("choose one of this customer's services", "service", "یکی از سرویس‌های مشتری را انتخاب کنید")
        if svc.panel_id != plan.panel_id:
            raise ManualInvoiceError("the plan is on another panel than the service", "plan", "پلن روی پنل دیگری است")
        if action == MI.ACT_RENEW and plan.type == PlanType.CUSTOM_VOLUME:
            raise ManualInvoiceError("a custom-volume plan cannot renew a service", "plan", "پلن حجم دلخواه برای تمدید نیست")
        out["service"] = svc
    return out


def _check_renewal(item: dict) -> None:
    if item["service_action"] != MI.ACT_RENEW:
        return
    from .services import waiting_renewal

    if waiting_renewal(item["service"]) is not None:
        raise ManualInvoiceError("this service already has a renewal waiting", "service",
                                 "این سرویس یک تمدید در انتظار دارد")


def _order_for(inv: MI, *, status=OrderStatus.PENDING_PAYMENT, source="admin") -> Order:
    return Order(user=inv.user, plan=inv.plan, service=inv.service, type=ORDER_TYPE[inv.service_action],
                 requested_account_name=inv.account_name or None if inv.service_action == MI.ACT_NEW else None,
                 amount=inv.amount, original_amount=inv.amount, status=status, source=source, manual_invoice=inv)


def _parse_dt(v, field):
    """ISO date-time (2026-11-03T14:30[+03:30]), Jalali "1405/08/12 14:30" (Persian digits ok) or a date."""
    import re
    from datetime import datetime

    if not v:
        return None
    if hasattr(v, "tzinfo"):
        return v
    raw = str(v).strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    bad = ManualInvoiceError(f"{field}: use a Jalali or ISO date and time", field, "تاریخ نامعتبر است")
    dt = None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        m = re.fullmatch(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?:[ T](\d{1,2}):(\d{2}))?", raw)
        if not m:
            raise bad
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
        hh, mm = int(m[4] or 0), int(m[5] or 0)
        try:
            if y < 1700:                                        # Jalali
                import jdatetime

                dt = jdatetime.datetime(y, mo, d, hh, mm).togregorian()
            else:
                dt = datetime(y, mo, d, hh, mm)
        except ValueError:
            raise bad
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


@transaction.atomic
def create_paid(user, staff, data: dict, *, receipt_image=None):
    """Mode A. Returns (invoice, payment, warnings)."""
    from apps.payments_sms.checks import image_sha256, normalize_ref
    from apps.payments_sms.models import BankCard, Payment, PaymentStatus
    from apps.payments_sms.services import approve_payment

    item = clean_item(user, data)
    _check_renewal(item)
    paid_at = _parse_dt(data.get("paid_at"), "paid_at") or timezone.now()
    if paid_at > timezone.now() + timedelta(minutes=5):
        raise ManualInvoiceError("the payment date is in the future", "paid_at", "تاریخ پرداخت در آینده است")
    method = METHODS.get(str(data.get("method") or "card"))
    if method is None:
        raise ManualInvoiceError("method must be card, cash or other", "method", "روش پرداخت نامعتبر است")
    card = None
    if data.get("bank_card"):
        card = BankCard.objects.filter(pk=data["bank_card"]).first()
        if card is None:
            raise ManualInvoiceError("bank card not found", "bank_card", "کارت پیدا نشد")
    inv = MI.objects.create(user=user, mode=MI.MODE_PAID, status=MI.OPEN, created_by=staff,
                            **{k: v for k, v in item.items() if k != "service" or v is not None})
    order = _order_for(inv)
    order.amount_unique = inv.amount
    order.unique_expire_at = paid_at
    order.amount_unique_lock = None                       # a manual order never reserves a unique amount
    order.save()
    ref = normalize_ref(str(data.get("receipt_ref") or ""))
    p = Payment(order=order, method=method, amount=inv.amount, status=PaymentStatus.PENDING, bank_card=card,
                receipt_ref=ref, receipt_amount=inv.amount)
    if receipt_image is not None:
        p.receipt_image = receipt_image
        p.receipt_sha256 = image_sha256(receipt_image)
    p.save()
    p = approve_payment(p.pk, actor=staff, bank_card=card, confirmed_at=paid_at, notify=False)
    inv.refresh_from_db()
    write_audit(action="manual_invoice.created_paid", staff=staff, target=inv, detail={
        "invoice": inv.number, "user": user.username, "amount": str(inv.amount), "paid_at": paid_at.isoformat(),
        "method": method, "tx": p.tx_number, "service_action": inv.service_action})
    return inv, p, duplicate_warnings(p)


def duplicate_warnings(p) -> list[dict]:
    """Same receipt image / same tracking number as another payment (customer or agency)."""
    from apps.agency.models import AgencyPayment
    from apps.payments_sms.models import Payment

    out = []
    if p.receipt_sha256:
        same = list(Payment.objects.filter(receipt_sha256=p.receipt_sha256).exclude(pk=p.pk).values_list("id", flat=True)[:5])
        same += [f"AP-{i:06d}" for i in AgencyPayment.objects.filter(receipt_sha256=p.receipt_sha256).values_list("id", flat=True)[:5]]
        if same:
            out.append({"kind": "duplicate_image", "payments": same})
    if p.receipt_ref:
        same = list(Payment.objects.filter(receipt_ref=p.receipt_ref).exclude(pk=p.pk).values_list("id", flat=True)[:5])
        same += [f"AP-{i:06d}" for i in AgencyPayment.objects.filter(receipt_ref=p.receipt_ref).values_list("id", flat=True)[:5]]
        if same:
            out.append({"kind": "duplicate_ref", "payments": same})
    return out


@transaction.atomic
def issue(user, staff, data: dict) -> MI:
    """Mode B: an open invoice the customer pays from their panel."""
    item = clean_item(user, data)
    due = _parse_dt(data.get("due_at"), "due_at")
    inv = MI.objects.create(user=user, mode=MI.MODE_ISSUED, status=MI.OPEN, created_by=staff, due_at=due,
                            **{k: v for k, v in item.items() if k != "service" or v is not None})
    write_audit(action="manual_invoice.issued", staff=staff, target=inv, detail={
        "invoice": inv.number, "user": user.username, "amount": str(inv.amount), "service_action": inv.service_action,
        "due_at": due.isoformat() if due else None})

    def tell():
        try:
            from apps.notifications.dispatch import notify_user
            from apps.notifications.models import NotificationType

            notify_user(user, title=f"فاکتور {inv.number} برای شما صادر شد",
                        body=f"{inv.label('fa')} · {int(inv.amount):,} تومان — از «سوابق خرید» پرداخت کنید.",
                        title_en=f"Invoice {inv.number} was issued for you",
                        body_en=f"{inv.label('en')} · {int(inv.amount):,} T — pay it from “History”.",
                        ntype=NotificationType.EVENT, via_site=True, via_bot=True, link="/history")
        except Exception as exc:  # noqa: BLE001
            log.warning("manual invoice notice failed: %s", exc)
    transaction.on_commit(tell)
    return inv


def open_order(inv: MI) -> Order | None:
    """An unfinished checkout of this invoice the customer can continue."""
    from apps.payments_sms.models import PaymentStatus

    for o in inv.orders.filter(status=OrderStatus.PENDING_PAYMENT).order_by("-created_at"):
        pay = getattr(o, "payment", None)
        if pay is not None and pay.status == PaymentStatus.PENDING:
            return o                                    # receipt under review — continue that one
        if pay is None and o.unique_expire_at and o.unique_expire_at > timezone.now():
            return o
    return None


@transaction.atomic
def pay(inv_id: int, user, *, source: str = "site") -> Order:
    """The customer pressed «پرداخت»: a normal checkout order for the invoice amount."""
    from .services import _assign_unique_amount, _reservation_deadline, expire_stale_reservations

    expire_stale_reservations()
    inv = MI.objects.select_for_update().filter(pk=inv_id, user=user, mode=MI.MODE_ISSUED).first()
    if inv is None:
        raise ManualInvoiceError("invoice not found", None, "فاکتور پیدا نشد")
    if inv.status != MI.OPEN:
        raise ManualInvoiceError(f"this invoice is {inv.status}", None, "این فاکتور دیگر باز نیست")
    existing = open_order(inv)
    if existing is not None:
        existing.reused = True
        return existing
    item = {"service_action": inv.service_action, "service": inv.service}
    _check_renewal(item)
    order = _order_for(inv, source=source)
    order.unique_expire_at = _reservation_deadline()
    _assign_unique_amount(order, inv.amount)
    order.reused = False
    write_audit(action="manual_invoice.checkout", staff=f"user:{user.username}", target=order,
                detail={"invoice": inv.number, "amount_unique": str(order.amount_unique)})
    from apps.notifications.live import push_payments_event

    push_payments_event("order_created", order_id=order.id)
    return order


def on_order_paid(order: Order) -> None:
    """Called inside mark_paid_and_fulfill for an order of a manual invoice."""
    from apps.payments_sms.models import Payment

    p = Payment.objects.filter(order=order).first()
    MI.objects.filter(pk=order.manual_invoice_id).update(
        status=MI.PAID, order=order, paid_at=(p.confirmed_at if p and p.confirmed_at else timezone.now()),
        updated_at=timezone.now())


def on_payment_void(order: Order, *, restored: bool = False) -> None:
    """A voided payment re-opens an issued invoice (cancels a mode-A one); a restore pays it again."""
    if not order.manual_invoice_id:
        return
    inv = MI.objects.filter(pk=order.manual_invoice_id).first()
    if inv is None:
        return
    if restored:
        inv.status = MI.PAID
    else:
        inv.status = MI.OPEN if inv.mode == MI.MODE_ISSUED else MI.CANCELLED
        if inv.status == MI.OPEN:
            inv.paid_at = None
    inv.save(update_fields=["status", "paid_at", "updated_at"])


@transaction.atomic
def cancel(inv_id: int, staff, reason: str = "") -> MI:
    inv = MI.objects.select_for_update().get(pk=inv_id)
    if inv.status != MI.OPEN or inv.mode != MI.MODE_ISSUED:
        raise ManualInvoiceError("only an open issued invoice can be cancelled", None, "فقط فاکتور باز قابل لغو است")
    for o in inv.orders.filter(status=OrderStatus.PENDING_PAYMENT):
        pay = getattr(o, "payment", None)
        if pay is not None and pay.status == "pending":
            raise ManualInvoiceError("a receipt for it is waiting for review — decide that first", None,
                                     "رسید این فاکتور در انتظار بررسی است — اول آن را بررسی کنید")
        o.status = OrderStatus.CANCELLED
        o.sync_unique_lock()
        o.save(update_fields=["status", "amount_unique_lock", "updated_at"])
    inv.status = MI.CANCELLED
    inv.save(update_fields=["status", "updated_at"])
    write_audit(action="manual_invoice.cancelled", staff=staff, target=inv, detail={"invoice": inv.number, "reason": reason})
    return inv


def row(inv: MI, lang: str = "fa", *, staff: bool = False) -> dict:
    pay = None
    if inv.order_id:
        from apps.payments_sms.models import Payment

        pay = Payment.objects.filter(order_id=inv.order_id).first()
    pending = open_order(inv) if inv.status == MI.OPEN and inv.mode == MI.MODE_ISSUED else None
    d = {"id": inv.id, "number": inv.number, "mode": inv.mode, "status": inv.status, "title": inv.label(lang),
         "plan": inv.plan_id, "plan_name": inv.plan.name_fa if inv.plan_id else "", "plan_name_en": inv.plan.name_en if inv.plan_id else "",
         "volume_gb": inv.volume_gb, "days": inv.days, "amount": inv.amount, "service_action": inv.service_action,
         "service": inv.service_id, "service_name": inv.service.panel_username if inv.service_id and inv.service else "",
         "account_name": inv.account_name, "due_at": inv.due_at, "paid_at": inv.paid_at, "created_at": inv.created_at,
         "overdue": bool(inv.status == MI.OPEN and inv.due_at and inv.due_at < timezone.now()),
         "order": inv.order_id, "tx_number": pay.tx_number if pay else None, "payment_id": pay.id if pay else None,
         "open_order": pending.id if pending else None, "note": inv.note if staff else ""}
    if staff:
        d["created_by"] = inv.created_by.username if inv.created_by_id else None
    return d
