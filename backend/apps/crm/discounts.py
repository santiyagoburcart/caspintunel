"""Discount codes (v1.26) — one engine for win-back codes (v1.20, apps.crm.retention)
and the codes made on the panel's "Discount codes" page.

`evaluate()` decides whether a customer may use a code for a purchase and how much it
takes off. It runs inside orders.services.create_order BEFORE the unique amount is
added, so the order's amount is already final and every payment check (SMS exact
amount, card-to-card review) works on what the customer really pays:

    original_amount − discount_amount = amount;  amount_unique = amount + surcharge

Uses. A code is "held" by an order that is paid / completed / failed (paid, not
provisioned yet), or pending payment while its reservation is alive or a receipt is
waiting for review. Rejected, expired and cancelled orders give the use back. The
customer's own still-unpaid invoices with the same code are not counted (buying again
replaces that invoice — create_order drops it), so a retry is never refused.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q
from django.utils import timezone

from .models import DiscountAppliesTo, DiscountAudience, DiscountCode, DiscountKind, DiscountType

D0 = Decimal(0)
ALPHA = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
HELD_STATUSES = ("paid", "completed", "failed")

# code → (Persian, English). {n} = an amount already formatted
MESSAGES = {
    "invalid": ("کد تخفیف معتبر نیست.", "This discount code is not valid."),
    "inactive": ("این کد تخفیف غیرفعال شده است.", "This discount code is disabled."),
    "not_started": ("این کد تخفیف هنوز شروع نشده است.", "This discount code is not active yet."),
    "expired": ("مهلت این کد تخفیف تمام شده است.", "This discount code has expired."),
    "not_for_you": ("این کد تخفیف برای حساب شما نیست.", "This discount code is not for your account."),
    "first_purchase": ("این کد فقط برای اولین خرید است.", "This code is for a first purchase only."),
    "not_for_plan": ("این کد تخفیف برای این پلن نیست.", "This discount code is not for this plan."),
    "not_for_new": ("این کد فقط برای تمدید است، نه خرید جدید.", "This code is for renewals only, not new purchases."),
    "not_for_renew": ("این کد فقط برای خرید جدید است، نه تمدید.", "This code is for new purchases only, not renewals."),
    "used_up": ("ظرفیت استفاده از این کد تمام شده است.", "This discount code has been used up."),
    "already_used": ("شما قبلاً از این کد استفاده کرده‌اید.", "You have already used this code."),
    "min_amount": ("این کد برای سفارش‌های حداقل {n} تومان است.", "This code needs an order of at least {n} Toman."),
}


class DiscountError(Exception):
    def __init__(self, code: str, **fmt):
        self.code, self.fmt = code, fmt
        fa, en = MESSAGES[code]
        self.fa, self.en = fa.format(**fmt), en.format(**fmt)
        super().__init__(self.en)

    def message(self, lang: str = "fa") -> str:
        return self.en if lang == "en" else self.fa


@dataclass
class Quote:
    code: DiscountCode
    original: Decimal
    discount: Decimal

    @property
    def final(self) -> Decimal:
        return self.original - self.discount


def normalize(raw: str | None) -> str:
    fa = "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩"
    return (raw or "").strip().translate(str.maketrans(fa, "01234567890123456789")).replace(" ", "").upper()


def random_code(prefix: str = "", length: int = 8) -> str:
    for _ in range(20):
        code = (prefix + "".join(secrets.choice(ALPHA) for _ in range(length))).upper()[:32]
        if not DiscountCode.objects.filter(code=code).exists():
            return code
    raise RuntimeError("could not allocate a unique code")


def _money(v) -> str:
    return f"{int(v):,}"


def is_renewal(order_type: str) -> bool:
    return order_type in ("renew", "addon_volume")


def held_orders(dc: DiscountCode, *, user=None, exclude_user_unpaid=None):
    """Orders that currently hold a use of `dc` (see the module doc)."""
    from apps.orders.models import Order

    now = timezone.now()
    qs = Order.objects.filter(discount_code=dc).filter(
        Q(status__in=HELD_STATUSES)
        | Q(status="pending_payment", unique_expire_at__gt=now)
        | Q(status="pending_payment", payment__status="pending")
    )
    if user is not None:
        qs = qs.filter(user=user)
    if exclude_user_unpaid is not None:
        qs = qs.exclude(Q(user=exclude_user_unpaid, status="pending_payment") & (Q(payment__isnull=True) | Q(payment__status="rejected")))
    return qs.distinct()


def has_paid_before(user) -> bool:
    from apps.orders.models import Order

    return Order.objects.filter(user=user, status__in=HELD_STATUSES).exclude(type="imported").exists()


def compute(dc: DiscountCode, amount: Decimal) -> Decimal:
    amount = Decimal(amount)
    if dc.discount_type == DiscountType.FIXED:
        off = Decimal(dc.amount_off or 0)
    else:
        off = (amount * Decimal(dc.percent or 0) / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        if dc.max_discount:
            off = min(off, Decimal(dc.max_discount))
    return max(D0, min(off, amount))


def evaluate(raw: str, *, user, plan, order_type: str, amount, now=None) -> Quote:
    """The discount `user` gets with code `raw` on this purchase, or DiscountError."""
    now = now or timezone.now()
    dc = DiscountCode.objects.filter(code=normalize(raw)).first()
    if dc is None:
        raise DiscountError("invalid")
    if dc.kind == DiscountKind.WINBACK and dc.user_id and dc.user_id != user.id:
        raise DiscountError("invalid")          # someone else's personal code: don't reveal it exists
    if not dc.is_active:
        raise DiscountError("inactive")
    if dc.starts_at and now < dc.starts_at:
        raise DiscountError("not_started")
    if dc.expires_at and now >= dc.expires_at:
        raise DiscountError("expired")
    if dc.user_id and dc.user_id != user.id:
        raise DiscountError("not_for_you")
    if dc.audience == DiscountAudience.SELECTED and not dc.customers.filter(pk=user.pk).exists():
        raise DiscountError("not_for_you")
    if dc.first_purchase_only and has_paid_before(user):
        raise DiscountError("first_purchase")
    if dc.plans.exists() and not dc.plans.filter(pk=plan.pk).exists():
        raise DiscountError("not_for_plan")
    if dc.applies_to == DiscountAppliesTo.RENEW and not is_renewal(order_type):
        raise DiscountError("not_for_new")
    if dc.applies_to == DiscountAppliesTo.NEW and is_renewal(order_type):
        raise DiscountError("not_for_renew")
    amount = Decimal(amount)
    if dc.min_order_amount and amount < Decimal(dc.min_order_amount):
        raise DiscountError("min_amount", n=_money(dc.min_order_amount))
    if dc.max_uses_per_customer is not None and \
            held_orders(dc, user=user, exclude_user_unpaid=user).count() >= dc.max_uses_per_customer:
        raise DiscountError("already_used")
    if dc.max_uses is not None and held_orders(dc, exclude_user_unpaid=user).count() >= dc.max_uses:
        raise DiscountError("used_up")
    if dc.kind == DiscountKind.WINBACK and dc.used_at is not None:
        raise DiscountError("already_used")
    return Quote(code=dc, original=amount, discount=compute(dc, amount))


def any_usable_for(user) -> bool:
    """Is there any code this customer might use now? (the bot only asks for a code then)"""
    now = timezone.now()
    live = (DiscountCode.objects.filter(is_active=True)
            .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)))
    return (live.filter(kind=DiscountKind.CAMPAIGN, audience=DiscountAudience.ALL).exists()
            or live.filter(kind=DiscountKind.CAMPAIGN, audience=DiscountAudience.SELECTED, customers=user).exists()
            or live.filter(kind=DiscountKind.WINBACK, user=user, used_at__isnull=True).exists())


# ------------------------------------------------------------------ reports
def stats(dc: DiscountCode, start=None, end=None) -> dict:
    """Uses (paid), customers, total discount and revenue (approved payments) of one code."""
    from django.db.models import Count, Sum

    from apps.payments_sms.models import Payment

    pays = Payment.objects.live().filter(status="approved", order__discount_code=dc)
    if start:
        pays = pays.filter(confirmed_at__gte=start)
    if end:
        pays = pays.filter(confirmed_at__lt=end)
    agg = pays.aggregate(uses=Count("order", distinct=True), customers=Count("order__user", distinct=True),
                         discount=Sum("order__discount_amount"), revenue=Sum("amount"))
    return {"uses": agg["uses"] or 0, "customers": agg["customers"] or 0,
            "discount": agg["discount"] or D0, "revenue": agg["revenue"] or D0,
            "held": held_orders(dc).count()}


def totals(start, end) -> dict:
    """All codes in a period (Accounting / Analytics): approved payments of orders with a code."""
    from django.db.models import Count, Sum

    from apps.payments_sms.models import Payment

    pays = Payment.objects.live().filter(status="approved", confirmed_at__gte=start, confirmed_at__lt=end,
                                         order__discount_code__isnull=False)
    agg = pays.aggregate(uses=Count("order", distinct=True), discount=Sum("order__discount_amount"), revenue=Sum("amount"))
    by_code = (pays.values("order__discount_code", "order__discount_code__code", "order__discount_code__kind")
               .annotate(uses=Count("order", distinct=True), customers=Count("order__user", distinct=True),
                         discount=Sum("order__discount_amount"), revenue=Sum("amount")).order_by("-discount"))
    return {"uses": agg["uses"] or 0, "discount": agg["discount"] or D0, "revenue": agg["revenue"] or D0,
            "by_code": [{"id": r["order__discount_code"], "code": r["order__discount_code__code"],
                         "kind": r["order__discount_code__kind"], "uses": r["uses"], "customers": r["customers"],
                         "discount": r["discount"] or D0, "revenue": r["revenue"] or D0} for r in by_code[:20]]}
