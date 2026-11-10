"""v1.53 (multi-tenant Phase 12, docs/multi-tenant.md §4 tenant_billing): the monthly store fee hook — OFF by default.

Our staff set it per store on «فروشگاه» (agency.accounting): amount, the first due day, reminder delay and the optional
suspension (off by default). The hourly job (`run`) then, per store with the fee on:

* on the due day: one ledger charge + one agency invoice of kind `store_fee` to the reseller (the existing invoices /
  payments / portal / SMS + Blu matching — nothing new to pay through), once per Jalali month (`TenantFeeInvoice` unique
  per store + month); `next_due` moves one Jalali month on;
* `remind_after_days` after the due day, still unpaid → a portal notice to the reseller + the store's own staff;
* only with `suspend_enabled`: `suspend_after_days` after the due day, still unpaid (not under review) → the store is
  suspended (its domains answer 404, like a manual suspension; audit + alert to us). Once every overdue fee invoice is paid
  (or voided) the store we suspended becomes active again by itself. A store our staff moved to another status meanwhile is
  left alone.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

import jdatetime
from django.db import transaction
from django.utils import timezone

from apps.common.jalali import jalali_day, parse_day, tehran_today
from apps.common.models import write_audit

from . import context

log = logging.getLogger("caspintunel")

MAX_AMOUNT = Decimal(10) ** 12


class FeeError(Exception):
    def __init__(self, en: str, fa: str, status: int = 400, field: str = ""):
        super().__init__(en)
        self.en, self.fa, self.status, self.field = en, fa, status, field

    def payload(self) -> dict:
        return {"detail": self.en, "detail_fa": self.fa, "field": self.field}


# ------------------------------------------------------------------ Jalali months
def period(d: date) -> str:
    j = jdatetime.date.fromgregorian(date=d)
    return f"{j.year:04d}-{j.month:02d}"


def add_month(d: date) -> date:
    """The same Jalali day next month (the last day of the month when it is shorter)."""
    j = jdatetime.date.fromgregorian(date=d)
    y, m = (j.year + 1, 1) if j.month == 12 else (j.year, j.month + 1)
    day = j.day
    while day > 28:
        try:
            return jdatetime.date(y, m, day).togregorian()
        except ValueError:
            day -= 1
    return jdatetime.date(y, m, day).togregorian()


def first_of_next_month(d: date | None = None) -> date:
    j = jdatetime.date.fromgregorian(date=d or tehran_today())
    y, m = (j.year + 1, 1) if j.month == 12 else (j.year, j.month + 1)
    return jdatetime.date(y, m, 1).togregorian()


# ------------------------------------------------------------------ settings (our staff)
def _fee(t, *, create: bool = False):
    from .models import TenantFee

    f = TenantFee.objects.filter(tenant=t).first()
    if f is None and create:
        f = TenantFee.objects.create(tenant=t)
    return f


def _open_invoices(t) -> list:
    from apps.agency.models import AgencyInvoice

    from .models import TenantFeeInvoice

    return list(TenantFeeInvoice.objects.filter(tenant=t, invoice__status__in=(AgencyInvoice.UNPAID, AgencyInvoice.PENDING))
                .select_related("invoice"))


def _suspend_on(t, fi) -> date | None:
    f = _fee(t)
    if f is None or not f.enabled or not f.suspend_enabled:
        return None
    return fi.due_date + timedelta(days=f.suspend_after_days)


def row(t) -> dict:
    from apps.agency import allocation

    from .models import TenantFeeInvoice

    f = _fee(t)
    inv_rows = []
    for fi in TenantFeeInvoice.objects.filter(tenant=t).select_related("invoice")[:12]:
        inv = fi.invoice
        inv_rows.append({"id": fi.id, "period": fi.period, "due_date": fi.due_date, "due_jalali": jalali_day(fi.due_date),
                         "amount": fi.amount, "invoice": inv.number if inv else None, "status": inv.status if inv else "",
                         "remaining": allocation.remaining(inv) if inv else Decimal(0),
                         "reminded_at": fi.reminded_at, "suspended_at": fi.suspended_at, "resumed_at": fi.resumed_at})
    nd = f.next_due if f else None
    return {
        "enabled": bool(f and f.enabled), "amount": f.amount if f else Decimal(0), "next_due": nd,
        "next_due_jalali": jalali_day(nd) if nd else "", "suggested_due": first_of_next_month(),
        "suggested_due_jalali": jalali_day(first_of_next_month()),
        "remind_after_days": f.remind_after_days if f else 3, "suspend_enabled": bool(f and f.suspend_enabled),
        "suspend_after_days": f.suspend_after_days if f else 10, "updated_by": f.updated_by if f else "",
        "updated_at": f.updated_at if f else None, "invoices": inv_rows,
        "suspended_by_fee": TenantFeeInvoice.objects.filter(tenant=t, suspended_at__isnull=False,
                                                            resumed_at__isnull=True).exists(),
    }


def _bool(v) -> bool:
    return v is True or str(v).lower() in ("1", "true", "yes", "on")


def _int(data, key, lo, hi, en, fa) -> int:
    try:
        n = int(str(data.get(key)).strip())
    except (TypeError, ValueError):
        raise FeeError(f"{key} must be a whole number", f"{fa} باید عدد صحیح باشد", field=key) from None
    if not lo <= n <= hi:
        raise FeeError(f"{en} must be {lo}–{hi}", f"{fa} باید بین {lo} و {hi} باشد", field=key)
    return n


@transaction.atomic
def save(t, data: dict, *, staff=None) -> dict:
    from .models import Tenant, TenantFee

    if t.is_default:
        raise FeeError("our own store has no fee", "فروشگاه اصلی هزینهٔ ماهانه ندارد", 403)
    Tenant.objects.select_for_update().filter(pk=t.pk).first()
    f = _fee(t, create=True)
    f = TenantFee.objects.select_for_update().get(pk=f.pk)
    before = _snap(f)
    if "amount" in data:
        try:
            amount = Decimal(str(data.get("amount") or 0).replace(",", "").strip())
        except InvalidOperation:
            raise FeeError("the fee must be a number (tomans)", "مبلغ اشتراک باید عدد (تومان) باشد", field="amount") from None
        if amount < 0 or amount >= MAX_AMOUNT or amount != amount.to_integral_value():
            raise FeeError("the fee must be a whole number of tomans, zero or more", "مبلغ اشتراک باید عدد صحیح تومان باشد",
                           field="amount")
        f.amount = amount
    if "next_due" in data:
        nd = parse_day(data.get("next_due")) if data.get("next_due") else None
        if data.get("next_due") and nd is None:
            raise FeeError("the due date is not a valid date", "تاریخ سررسید معتبر نیست", field="next_due")
        if nd is not None and nd != f.next_due and nd < tehran_today():
            raise FeeError("the first due date cannot be in the past", "تاریخ سررسید نمی‌تواند گذشته باشد", field="next_due")
        f.next_due = nd
    if "remind_after_days" in data:
        f.remind_after_days = _int(data, "remind_after_days", 0, 60, "the reminder delay", "فاصلهٔ یادآوری")
    if "suspend_after_days" in data:
        f.suspend_after_days = _int(data, "suspend_after_days", 1, 90, "the suspension delay", "مهلت تعلیق")
    if "suspend_enabled" in data:
        f.suspend_enabled = _bool(data.get("suspend_enabled"))
    if "enabled" in data:
        f.enabled = _bool(data.get("enabled"))
    if f.enabled:
        if f.amount <= 0:
            raise FeeError("set the monthly fee before turning it on", "پیش از روشن‌کردن، مبلغ اشتراک ماهانه را وارد کنید",
                           field="amount")
        if f.next_due is None:
            raise FeeError("set the first due date before turning it on", "پیش از روشن‌کردن، تاریخ اولین سررسید را وارد کنید",
                           field="next_due")
        if not t.reseller_username:
            raise FeeError("this store has no reseller to invoice", "این فروشگاه نماینده‌ای برای صدور فاکتور ندارد")
    f.updated_by = getattr(staff, "username", "")[:150]
    f.save()
    after = _snap(f)
    if after != before:
        write_audit(action="store.fee_updated", staff=staff, target=t, detail={"tenant": t.pk, "before": before, "after": after})
    return row(t)


def _snap(f) -> dict:
    return {"enabled": f.enabled, "amount": str(f.amount), "next_due": f.next_due.isoformat() if f.next_due else None,
            "remind_after_days": f.remind_after_days, "suspend_enabled": f.suspend_enabled,
            "suspend_after_days": f.suspend_after_days}


# ------------------------------------------------------------------ the hourly job
def _store_staff_alert(t, text: str, key: str) -> None:
    """The store's own staff (owner …) in the store's context — never ours."""
    from apps.common.staff_alert import alert_staff

    try:
        with context.tenant_context(t.pk):
            alert_staff(text, perm="settings.manage", dedupe_key=key, ttl=7 * 86400)
    except Exception:  # noqa: BLE001
        log.exception("fees: store staff alert failed for %s", t.slug)


def _our_alert(text: str, key: str, *, silent: bool = True) -> None:
    from apps.common.staff_alert import alert_staff

    try:
        alert_staff(text, perm="agency.accounting", platform=True, silent=silent, dedupe_key=key, ttl=7 * 86400)
    except Exception:  # noqa: BLE001
        log.exception("fees: staff alert failed")


def _notice(t, *, kind: str, title: str, title_en: str, body: str, body_en: str) -> None:
    from apps.agency.billing import notice

    try:
        notice(admin=t.reseller_username, kind=kind, title=title, title_en=title_en, body=body, body_en=body_en)
    except Exception:  # noqa: BLE001
        log.exception("fees: reseller notice failed for %s", t.slug)


def issue(fee_id: int, today: date) -> dict | None:
    """The invoice of the fee due on or before `today` (once per Jalali month); moves `next_due` one month on."""
    from apps.agency import billing
    from apps.agency.models import AgencyInvoice, LedgerEntry

    from .models import Tenant, TenantFee, TenantFeeInvoice

    with transaction.atomic():
        f = TenantFee.objects.select_for_update().select_related("tenant").get(pk=fee_id)
        t = f.tenant
        if not (f.enabled and f.amount > 0 and f.next_due and f.next_due <= today) or t.is_default \
                or t.status == Tenant.CLOSED or not t.reseller_username:
            return None
        due, per = f.next_due, period(f.next_due)
        fi, created = TenantFeeInvoice.objects.get_or_create(tenant=t, period=per,
                                                             defaults={"due_date": due, "amount": f.amount})
        if created:
            jy, jm = per.split("-")
            entry = LedgerEntry.objects.create(admin_username=t.reseller_username, kind=LedgerEntry.KIND_CHARGE,
                                               amount=f.amount, date=due, created_by="system",
                                               note=f"store monthly fee {jy}/{jm} — {t.name}"[:255])
            fi.invoice = billing.issue_for_entry(entry, by="system", kind=AgencyInvoice.KIND_STORE_FEE)
            fi.save(update_fields=["invoice"])
            write_audit(action="store.fee_invoiced", target=t,
                        detail={"tenant": t.pk, "period": per, "amount": str(f.amount),
                                "invoice": fi.invoice.number if fi.invoice else None})
        f.next_due = add_month(due)
        f.save(update_fields=["next_due", "updated_at"])
    if created:
        num = fi.invoice.number if fi.invoice else ""
        _our_alert(f"🧾 اشتراک ماهانهٔ فروشگاه {t.name} ({t.reseller_username}) صادر شد: {num} · {f.amount:,} تومان ({per}).\n"
                   f"Store {t.slug}: monthly fee invoice {num}, {f.amount:,} T.", f"tenancy:fee:issued:{t.pk}:{per}")
    return {"store": t.slug, "period": per, "created": created}


def _remind(fi, today: date) -> bool:
    from apps.agency import allocation

    from .models import TenantFeeInvoice

    t, f = fi.tenant, fi.tenant.fee
    if not f.remind_after_days or fi.due_date + timedelta(days=f.remind_after_days) > today:
        return False
    if not TenantFeeInvoice.objects.filter(pk=fi.pk, reminded_at__isnull=True).update(reminded_at=timezone.now()):
        return False
    left = allocation.remaining(fi.invoice)
    sus = _suspend_on(t, fi)
    sus_fa = f" — اگر تا {jalali_day(sus)} پرداخت نشود، فروشگاه معلق می‌شود." if sus else ""
    sus_en = f" — the store is suspended if it is still unpaid on {sus.isoformat()}." if sus else ""
    _notice(t, kind="store_fee_due", title=f"یادآوری: اشتراک فروشگاه {fi.period.replace('-', '/')} پرداخت نشده",
            title_en=f"Reminder: store fee {fi.period} is unpaid",
            body=f"فاکتور {fi.invoice.number} · {left:,} تومان{sus_fa}", body_en=f"Invoice {fi.invoice.number} · {left:,} T{sus_en}")
    _store_staff_alert(t, f"🔔 اشتراک ماهانهٔ فروشگاه ({fi.period.replace('-', '/')}) هنوز پرداخت نشده: فاکتور {fi.invoice.number} · "
                          f"{left:,} تومان. پرداخت از پنل نمایندگی (/agency/).{sus_fa}", f"tenancy:fee:remind:{fi.pk}")
    write_audit(action="store.fee_reminded", target=t, detail={"tenant": t.pk, "period": fi.period})
    return True


def _suspend(fi, today: date) -> bool:
    from .models import Tenant, TenantFeeInvoice
    from .stores import update

    t, f = fi.tenant, fi.tenant.fee
    if not (f.enabled and f.suspend_enabled) or fi.due_date + timedelta(days=f.suspend_after_days) > today:
        return False
    t.refresh_from_db()
    if t.status != Tenant.ACTIVE:
        return False
    with transaction.atomic():
        if not TenantFeeInvoice.objects.filter(pk=fi.pk, suspended_at__isnull=True).update(suspended_at=timezone.now()):
            return False
        update(t, {"status": Tenant.SUSPENDED})
        write_audit(action="store.fee_suspended", target=t, detail={"tenant": t.pk, "period": fi.period,
                                                                    "invoice": fi.invoice.number})
    _notice(t, kind="store_suspended", title="فروشگاه به خاطر اشتراک پرداخت‌نشده معلق شد",
            title_en="Store suspended: the monthly fee is unpaid",
            body=f"فاکتور {fi.invoice.number} را بپردازید؛ پس از تأیید پرداخت، فروشگاه خودکار فعال می‌شود.",
            body_en=f"Pay invoice {fi.invoice.number}; the store comes back by itself once the payment is approved.")
    _our_alert(f"⛔ فروشگاه {t.name} ({t.reseller_username}) به خاطر اشتراک پرداخت‌نشدهٔ {fi.period.replace('-', '/')} معلق شد "
               f"(فاکتور {fi.invoice.number}).\nStore {t.slug} suspended: fee {fi.period} unpaid.",
               f"tenancy:fee:suspended:{fi.pk}", silent=False)
    return True


def _resume(t, today: date) -> bool:
    """A store WE suspended for an unpaid fee comes back once no overdue fee invoice is unpaid / under review."""
    from apps.agency.models import AgencyInvoice

    from .models import Tenant, TenantFeeInvoice
    from .stores import update

    held = list(TenantFeeInvoice.objects.filter(tenant=t, suspended_at__isnull=False, resumed_at__isnull=True))
    if not held:
        return False
    t.refresh_from_db()
    now = timezone.now()
    if t.status != Tenant.SUSPENDED:                    # our staff changed it meanwhile — stop tracking, change nothing
        TenantFeeInvoice.objects.filter(pk__in=[h.pk for h in held]).update(resumed_at=now)
        return False
    if TenantFeeInvoice.objects.filter(tenant=t, invoice__status__in=(AgencyInvoice.UNPAID, AgencyInvoice.PENDING)).exists():
        return False
    with transaction.atomic():
        TenantFeeInvoice.objects.filter(pk__in=[h.pk for h in held]).update(resumed_at=now)
        update(t, {"status": Tenant.ACTIVE})
        write_audit(action="store.fee_resumed", target=t, detail={"tenant": t.pk, "periods": [h.period for h in held]})
    _notice(t, kind="store_resumed", title="فروشگاه دوباره فعال شد", title_en="Store active again",
            body="اشتراک پرداخت شد و فروشگاه دوباره در دسترس است.", body_en="The fee is paid and the store is reachable again.")
    _our_alert(f"✅ فروشگاه {t.name} ({t.reseller_username}) پس از پرداخت اشتراک دوباره فعال شد.\nStore {t.slug} active again.",
               f"tenancy:fee:resumed:{t.pk}:{held[-1].pk}")
    return True


def run(today: date | None = None) -> dict:
    from apps.agency.models import AgencyInvoice

    from .models import Tenant, TenantFee, TenantFeeInvoice

    today = today or tehran_today()
    out = {"issued": [], "reminded": [], "suspended": [], "resumed": []}
    for fid in TenantFee.objects.filter(enabled=True, amount__gt=0, next_due__lte=today).values_list("id", flat=True):
        try:
            r = issue(fid, today)
            if r and r["created"]:
                out["issued"].append(f"{r['store']}:{r['period']}")
        except Exception:  # noqa: BLE001 — one store never stops the others
            log.exception("fees: issuing fee %s failed", fid)
    unpaid = (TenantFeeInvoice.objects.filter(invoice__status=AgencyInvoice.UNPAID, tenant__fee__enabled=True)
              .exclude(tenant__status=Tenant.CLOSED).select_related("tenant__fee", "invoice"))
    for fi in unpaid:
        try:
            if fi.reminded_at is None and _remind(fi, today):
                out["reminded"].append(f"{fi.tenant.slug}:{fi.period}")
            if fi.suspended_at is None and _suspend(fi, today):
                out["suspended"].append(f"{fi.tenant.slug}:{fi.period}")
        except Exception:  # noqa: BLE001
            log.exception("fees: reminder / suspension failed for %s", fi.pk)
    for tid in (TenantFeeInvoice.objects.filter(suspended_at__isnull=False, resumed_at__isnull=True)
                .values_list("tenant_id", flat=True).distinct()):
        try:
            t = Tenant.objects.get(pk=tid)
            if _resume(t, today):
                out["resumed"].append(t.slug)
        except Exception:  # noqa: BLE001
            log.exception("fees: resume failed for store %s", tid)
    return out


# ------------------------------------------------------------------ the store's own dashboard
def store_banner(tenant_id: int | None) -> dict | None:
    """Unpaid fee invoices of the store (amount, the earliest suspension day) — None when nothing is open."""
    from apps.agency import allocation

    from .models import Tenant

    if not tenant_id:
        return None
    t = Tenant.objects.filter(pk=tenant_id).first()
    if t is None:
        return None
    rows = _open_invoices(t)
    if not rows:
        return None
    sus = [d for d in (_suspend_on(t, fi) for fi in rows if fi.invoice.status == "unpaid") if d]
    first = min(sus) if sus else None
    return {"count": len(rows), "amount": sum((allocation.remaining(fi.invoice) for fi in rows), Decimal(0)),
            "invoices": [fi.invoice.number for fi in rows], "suspend_on": first,
            "suspend_on_jalali": jalali_day(first) if first else "",
            "under_review": any(fi.invoice.status == "pending" for fi in rows)}
