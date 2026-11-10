"""v1.53 (multi-tenant Phase 10, docs/multi-tenant.md §14): a reseller store's own data as a zip of JSON + CSV.

* Who: the store's staff with `store.export` while we allow it (`Tenant.export_allowed`, «فروشگاه»), at most one per 6 h;
  our staff on «فروشگاه» for any store (no gap). One export runs at a time per store.
* What: customers, services, orders, payments, scheduled renewals, tickets (+ messages, topics, attachment names), discount
  codes, plans, branding, store settings, pages and receiving cards — every dataset is an EXPLICIT field list (below), read
  inside the store's tenant context (scoped managers), so other stores' rows and our own data never get in. Never: password
  hashes, tokens / secrets (the bot token lives in TenantBot, never read here), our panel names, Blu / SMS links, our staff's
  names (shown as «support»). Card numbers are masked except the last 4.
* How: `start` → Celery `build_export_task` (in the store's context, progress per dataset) → file under media/exports/
  (nginx 404s it) → `link` makes a ONE-TIME link (sha256 stored, a new link replaces the old one) that works until the
  export expires 24 h after it was ready, on the host it was made for → `consume` serves it once. `cleanup` (hourly)
  deletes expired files and fails stuck jobs. Every step is audit-logged.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
import secrets
import zipfile
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.common.models import write_audit

from . import context

log = logging.getLogger("caspintunel")

FORMAT_VERSION = 1
KEEP = timedelta(hours=24)              # a ready export (and its links) lives this long
STORE_GAP = timedelta(hours=6)          # the store may ask for one export per 6 h (our staff: no gap)
STUCK = timedelta(hours=2)              # queued / running longer than this = failed
FILE_CAP = 5 * 1024 * 1024              # branding images bigger than this are left out
SUPPORT = "support"                     # how our staff appear in a store's export


class ExportError(Exception):
    def __init__(self, en: str, fa: str, status: int = 400, code: str = "invalid", **extra):
        super().__init__(en)
        self.en, self.fa, self.status, self.code, self.extra = en, fa, status, code, extra

    def payload(self) -> dict:
        return {"detail": self.en, "detail_fa": self.fa, "code": self.code, **self.extra}


# ------------------------------------------------------------------ masking / values
def mask_card(value) -> str:
    """Only the last 4 digits stay: ************1234 (empty stays empty)."""
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if not digits:
        return ""
    return "*" * max(0, len(digits) - 4) + digits[-4:]


def _plain(v):
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    return v


class _Staff:
    """Staff ids → the name a store may see: its own staff by username, anyone else (our staff) as «support»."""

    def __init__(self, tenant_id: int):
        from apps.accounts.models import Staff

        self.own = dict(Staff.objects.filter(tenant_id=tenant_id).values_list("id", "username"))

    def name(self, staff_id) -> str:
        if not staff_id:
            return ""
        return self.own.get(staff_id, SUPPORT)


# ------------------------------------------------------------------ datasets (explicit fields only)
def _customers(ctx):
    from apps.accounts.models import User

    fields = ("id", "username", "name", "email", "email_verified", "phone", "telegram_id", "telegram_username",
              "bank_card_number", "referral_code", "referred_by_id", "source", "language", "is_active", "is_legacy",
              "admin_note", "terms_accepted_at", "created_at", "deleted_at", "delete_reason", "purged_at")
    for r in User.objects.order_by("id").values(*fields).iterator(chunk_size=500):
        r["bank_card_number"] = mask_card(r["bank_card_number"])
        yield r


def _services(ctx):
    from apps.panel.models import Service

    fields = ("id", "user_id", "panel_username", "subscription_url", "status", "expire_strategy", "data_limit", "data_used",
              "expire_at", "on_hold_duration", "on_hold_timeout", "online_at", "last_synced_at", "device_limit",
              "current_plan_id", "source", "created_at", "updated_at")
    yield from Service.objects.order_by("id").values(*fields).iterator(chunk_size=500)


def _orders(ctx):
    from apps.orders.models import Order

    fields = ("id", "user_id", "service_id", "plan_id", "type", "requested_account_name", "custom_volume_gb", "amount",
              "discount_amount", "original_amount", "discount_code_id", "discount_code_text", "amount_unique",
              "unique_expire_at", "status", "source", "provision_error", "provision_failed_at", "created_at", "updated_at")
    yield from Order.objects.order_by("id").values(*fields).iterator(chunk_size=500)


def _payments(ctx):
    from apps.payments_sms.models import Payment

    fields = ("id", "number", "order_id", "method", "amount", "status", "receipt_ref", "receipt_amount",
              "bank_card__card_number", "gateway_ref", "confirmed_by", "confirmed_by_staff_id", "confirmed_at",
              "reject_reason", "voided_at", "voided_by_id", "void_reason", "auto_rule", "shortfall", "created_at")
    for r in Payment.objects.order_by("id").values(*fields).iterator(chunk_size=500):
        r["card"] = mask_card(r.pop("bank_card__card_number"))
        r["confirmed_by_staff"] = ctx["staff"].name(r.pop("confirmed_by_staff_id"))
        r["voided_by"] = ctx["staff"].name(r.pop("voided_by_id"))
        yield r


def _renewals(ctx):
    from apps.orders.models import ScheduledRenewal

    fields = ("id", "service_id", "plan_id", "order_id", "renewal_mode", "carry_over_data", "data_limit", "applied_at",
              "created_at")
    yield from ScheduledRenewal.objects.order_by("id").values(*fields).iterator(chunk_size=500)


def _ticket_topics(ctx):
    from apps.tickets.models import TicketTopic

    fields = ("id", "name_fa", "name_en", "description_fa", "description_en", "requires_active_service", "is_active",
              "sort_order", "created_at")
    yield from TicketTopic.objects.order_by("id").values(*fields).iterator(chunk_size=500)


def _tickets(ctx):
    from apps.tickets.models import Ticket

    fields = ("id", "number", "user_id", "topic_id", "subject", "status", "priority", "assigned_to_id", "service_id",
              "order_id", "source", "first_response_at", "last_activity_at", "closed_by_id", "closed_by_kind", "closed_at",
              "created_at")
    for r in Ticket.objects.order_by("id").values(*fields).iterator(chunk_size=500):
        r["assigned_to"] = ctx["staff"].name(r.pop("assigned_to_id"))
        r["closed_by"] = ctx["staff"].name(r.pop("closed_by_id"))
        yield r


def _ticket_messages(ctx):
    from apps.tickets.models import TicketMessage

    fields = ("id", "ticket_id", "author_user_id", "author_staff_id", "body", "is_internal", "channel", "created_at")
    for r in TicketMessage.objects.order_by("id").values(*fields).iterator(chunk_size=500):
        staff_id = r.pop("author_staff_id")
        r["author_staff"] = ctx["staff"].name(staff_id)
        yield r


def _ticket_attachments(ctx):
    from apps.tickets.models import TicketAttachment

    fields = ("id", "message_id", "original_name", "content_type", "size", "created_at")   # names only, never the files
    yield from TicketAttachment.objects.order_by("id").values(*fields).iterator(chunk_size=500)


def _discounts(ctx):
    from apps.crm.models import DiscountCode

    fields = ("id", "code", "kind", "name", "is_active", "starts_at", "expires_at", "user_id", "discount_type", "percent",
              "max_discount", "amount_off", "audience", "first_purchase_only", "applies_to", "max_uses",
              "max_uses_per_customer", "min_order_amount", "note", "order_id", "used_at", "created_at")
    rows = list(DiscountCode.objects.order_by("id").values(*fields))
    ids = [r["id"] for r in rows]
    customers, plans = {}, {}
    for code_id, user_id in DiscountCode.customers.through.objects.filter(discountcode_id__in=ids).values_list(
            "discountcode_id", "user_id"):
        customers.setdefault(code_id, []).append(user_id)
    for code_id, plan_id in DiscountCode.plans.through.objects.filter(discountcode_id__in=ids).values_list(
            "discountcode_id", "plan_id"):
        plans.setdefault(code_id, []).append(plan_id)
    for r in rows:
        r["customer_ids"] = sorted(customers.get(r["id"], []))
        r["plan_ids"] = sorted(plans.get(r["id"], []))
        yield r


def _plans(ctx):
    from apps.plans.models import Plan

    fields = ("id", "name_fa", "name_en", "desc_fa", "desc_en", "category_fa", "category_en", "type", "data_limit",
              "duration_days", "device_limit", "price", "discount_percent", "is_active", "renewable_when_inactive",
              "sort_order", "renewal_mode", "carry_over_data", "group_ids", "min_gb", "max_gb", "price_per_gb")
    yield from Plan.objects.order_by("id").values(*fields).iterator(chunk_size=500)


def _branding(ctx):
    from apps.settings_app.models import TenantBranding

    fields = ("site_name_fa", "site_name_en", "logo", "favicon", "bot_description_fa", "bot_description_en",
              "support_telegram", "bot_support_telegram", "bot_support_text_fa", "bot_support_text_en", "qr_background",
              "qr_background_custom", "meta_description", "support_email", "updated_at")
    yield from TenantBranding.objects.values(*fields)


def _settings(ctx):
    from apps.settings_app.branding import TENANT_KEYS
    from apps.settings_app.models import TenantSetting

    yield from TenantSetting.objects.filter(key__in=TENANT_KEYS).order_by("key").values("key", "value", "value_type")


def _pages(ctx):
    from apps.settings_app.models import Page

    yield from Page.objects.order_by("slug").values("slug", "title_fa", "title_en", "body_fa", "body_en", "is_active",
                                                    "updated_at")


def _cards(ctx):
    from apps.payments_sms.models import BankCard

    for r in BankCard.objects.order_by("sort_order", "id").values("id", "card_number", "holder_name", "bank_name",
                                                                  "sort_order", "is_active", "created_at"):
        r["card_number"] = mask_card(r["card_number"])
        yield r


# name, rows, (fa, en) label for the README
DATASETS = [
    ("customers", _customers, ("مشتری‌ها", "customers")),
    ("services", _services, ("سرویس‌ها", "services")),
    ("orders", _orders, ("سفارش‌ها", "orders")),
    ("payments", _payments, ("پرداخت‌ها", "payments")),
    ("scheduled_renewals", _renewals, ("تمدیدهای در صف", "queued renewals")),
    ("tickets", _tickets, ("تیکت‌ها", "tickets")),
    ("ticket_messages", _ticket_messages, ("پیام‌های تیکت", "ticket messages")),
    ("ticket_attachments", _ticket_attachments, ("پیوست‌های تیکت (فقط نام)", "ticket attachments (names only)")),
    ("ticket_topics", _ticket_topics, ("موضوعات تیکت", "ticket topics")),
    ("discount_codes", _discounts, ("کدهای تخفیف", "discount codes")),
    ("plans", _plans, ("پلن‌ها", "plans")),
    ("branding", _branding, ("برندینگ", "branding")),
    ("settings", _settings, ("تنظیمات فروشگاه", "store settings")),
    ("pages", _pages, ("صفحه‌ها", "pages")),
    ("bank_cards", _cards, ("کارت‌های دریافت (پوشیده)", "receiving cards (masked)")),
]

README = """Store backup — {name} ({slug})
Created: {created} (UTC) · format {version}

json/<name>.json  every row as a JSON list
csv/<name>.csv    the same rows (UTF-8, Excel-ready)
files/            branding images (logo, favicon, QR background), when present

Not included: passwords, bot token or any other secret, ticket attachment files (names only), receipts.
Card numbers keep only the last 4 digits. Replies by our support team show as "support".

پشتیبان فروشگاه — {name}
پوشه‌های json و csv هر کدام همهٔ ردیف‌ها را دارند. رمزها، توکن ربات و فایل پیوست‌ها/رسیدها در آن نیست؛
از شمارهٔ کارت‌ها فقط ۴ رقم آخر مانده است. پاسخ‌های پشتیبانی ما با نام «support» آمده‌اند.
"""


# ------------------------------------------------------------------ files
def media_root() -> str:
    return str(settings.MEDIA_ROOT)


def _path(rel: str) -> str:
    return os.path.join(media_root(), rel)


def _delete_file(rel: str) -> None:
    if not rel:
        return
    try:
        os.remove(_path(rel))
    except FileNotFoundError:
        pass
    except OSError:
        log.exception("export: could not delete %s", rel)


# ------------------------------------------------------------------ start
def _tenant():
    from .models import Tenant

    tid = context.store_id()
    if tid is None:
        raise ExportError("store exports exist only for reseller stores", "خروجی فقط برای فروشگاه نمایندگان است", 404,
                          "not_store")
    return Tenant.objects.get(pk=tid)


def next_allowed_at(t) -> datetime | None:
    """When the store may ask for its next export (None = now)."""
    from .models import TenantExport

    last = (TenantExport.objects.filter(by_platform=False).exclude(state=TenantExport.FAILED)
            .order_by("-created_at").values_list("created_at", flat=True).first())
    if last is None or last + STORE_GAP <= timezone.now():
        return None
    return last + STORE_GAP


@transaction.atomic
def start(*, staff=None, platform: bool = False):
    """Queue an export of the CURRENT store (its tenant context must be set)."""
    from .models import Tenant, TenantExport

    t = _tenant()
    Tenant.objects.select_for_update().filter(pk=t.pk).first()       # one start at a time per store
    if not platform and not t.export_allowed:
        raise ExportError("exports are not enabled for this store", "دریافت خروجی برای این فروشگاه فعال نشده است", 403,
                          "not_allowed")
    if TenantExport.objects.filter(state__in=(TenantExport.QUEUED, TenantExport.RUNNING)).exists():
        raise ExportError("an export is already being prepared", "یک خروجی در حال آماده‌سازی است", 409, "busy")
    if not platform:
        nxt = next_allowed_at(t)
        if nxt is not None:
            from apps.common.jalali import to_jalali_str

            raise ExportError(f"one export per 6 hours — next at {nxt.isoformat()}",
                              f"هر ۶ ساعت یک خروجی — خروجی بعدی از {to_jalali_str(nxt)}", 429, "too_soon",
                              next_allowed_at=nxt.isoformat())
    e = TenantExport.objects.create(requested_by=getattr(staff, "username", "")[:150], by_platform=platform)
    write_audit(action="store.export_requested", staff=staff, target=e,
                detail={"tenant": t.pk, "export": e.pk, "by_platform": platform})
    tid = t.pk

    def queue():
        from .tasks import build_export_task

        with context.tenant_context(tid):                 # the task runs in the store (celery_ctx header)
            build_export_task.delay(e.pk)
    transaction.on_commit(queue)
    return e


# ------------------------------------------------------------------ build (Celery, in the store's context)
def _write_dataset(zf, name, rows_fn, ctx) -> int:
    count = 0
    with zf.open(f"json/{name}.json", "w") as raw:
        out = io.TextIOWrapper(raw, encoding="utf-8")
        out.write("[")
        columns: list[str] = []
        for r in rows_fn(ctx):
            r = {k: _plain(v) for k, v in r.items()}
            for k in r:
                if k not in columns:
                    columns.append(k)
            out.write(("\n" if count == 0 else ",\n") + json.dumps(r, ensure_ascii=False))
            count += 1
        out.write("\n]\n")
        out.flush()
        out.detach()
    with zf.open(f"csv/{name}.csv", "w") as raw:
        out = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
        w = csv.writer(out)
        if columns:
            w.writerow(columns)
            for r in rows_fn(ctx):
                w.writerow([_csv(_plain(r.get(c))) for c in columns])
        out.flush()
        out.detach()
    return count


def _csv(v):
    if v is None:
        return ""
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    return v


def _branding_files(zf) -> list[str]:
    from apps.settings_app.models import TenantBranding

    b = TenantBranding.objects.first()
    added = []
    for field in ("logo", "favicon", "qr_background_custom"):
        f = getattr(b, field, None) if b else None
        name = getattr(f, "name", "") if f else ""
        if not name:
            continue
        try:
            if f.size > FILE_CAP:
                continue
            with f.open("rb") as fh:
                zf.writestr(f"files/branding/{field}{os.path.splitext(name)[1][:8]}", fh.read())
            added.append(field)
        except Exception:  # noqa: BLE001 — a missing image never fails the export
            log.warning("export: branding file %s missing", name)
    return added


def build(export_id: int) -> str:
    from .models import Tenant, TenantExport

    if context.store_id() is None:
        return "not in a store"
    claimed = TenantExport.objects.filter(pk=export_id, state=TenantExport.QUEUED).update(
        state=TenantExport.RUNNING, started_at=timezone.now(), progress=1)
    if not claimed:
        return "not queued"
    e = TenantExport.objects.get(pk=export_id)
    t = Tenant.objects.get(pk=context.store_id())
    rel = f"exports/{t.pk}/{secrets.token_urlsafe(24)}.zip"
    os.makedirs(os.path.dirname(_path(rel)), exist_ok=True)
    counts: dict[str, int] = {}
    try:
        ctx = {"staff": _Staff(t.pk)}
        with zipfile.ZipFile(_path(rel), "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for i, (name, rows_fn, _label) in enumerate(DATASETS):
                TenantExport.objects.filter(pk=e.pk).update(step=name, progress=max(1, int(i * 95 / len(DATASETS))))
                counts[name] = _write_dataset(zf, name, rows_fn, ctx)
            files = _branding_files(zf)
            created = timezone.now()
            zf.writestr("manifest.json", json.dumps({
                "format_version": FORMAT_VERSION, "store": {"name": t.name, "slug": t.slug}, "created_at": created.isoformat(),
                "datasets": counts, "files": files, "card_numbers": "masked (last 4 digits)", "staff_names": "ours = support",
            }, ensure_ascii=False, indent=2))
            zf.writestr("README.txt", README.format(name=t.name, slug=t.slug, created=created.strftime("%Y-%m-%d %H:%M"),
                                                    version=FORMAT_VERSION))
    except Exception as exc:  # noqa: BLE001
        log.exception("export %s of store %s failed", export_id, t.slug)
        _delete_file(rel)
        TenantExport.objects.filter(pk=e.pk).update(state=TenantExport.FAILED, error=f"{exc.__class__.__name__}: {exc}"[:500],
                                                     finished_at=timezone.now())
        write_audit(action="store.export_failed", target=e, detail={"tenant": t.pk, "export": e.pk, "error": str(exc)[:200]})
        return "failed"
    now = timezone.now()
    TenantExport.objects.filter(pk=e.pk).update(
        state=TenantExport.READY, progress=100, step="", file=rel, size=os.path.getsize(_path(rel)), counts=counts,
        finished_at=now, expires_at=now + KEEP)
    write_audit(action="store.export_ready", target=e, detail={"tenant": t.pk, "export": e.pk, "counts": counts})
    return "ready"


# ------------------------------------------------------------------ one-time links
def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def link(export_id: int, *, staff=None, platform: bool = False) -> dict:
    """A one-time link for a READY export of the current store. Making a new link ends the previous one."""
    from .models import TenantExport

    t = _tenant()
    e = TenantExport.objects.filter(pk=export_id).first()
    if e is None:
        raise ExportError("export not found", "خروجی پیدا نشد", 404, "not_found")
    if not platform and not t.export_allowed:
        raise ExportError("exports are not enabled for this store", "دریافت خروجی برای این فروشگاه فعال نشده است", 403,
                          "not_allowed")
    now = timezone.now()
    if e.state != TenantExport.READY or not e.expires_at or e.expires_at <= now:
        raise ExportError("this export is not ready or has expired", "این خروجی آماده نیست یا منقضی شده است", 410, "gone")
    token = secrets.token_urlsafe(32)
    TenantExport.objects.filter(pk=e.pk).update(link_hash=_hash(token), link_scope="platform" if platform else "store",
                                               link_expires_at=e.expires_at)
    write_audit(action="store.export_link", staff=staff, target=e,
                detail={"tenant": t.pk, "export": e.pk, "scope": "platform" if platform else "store"})
    return {"url": f"/api/v1/exports/download/{t.pk}/{token}/", "expires_at": e.expires_at,
            "message": "Download started — this link works once", "message_fa": "دریافت فایل شروع شد — این لینک فقط یک بار کار می‌کند"}


def consume(tenant_id: int, token: str):
    """The export a one-time link points to (and the link is spent), or ExportError. Runs on the link's own host only:
    a store link on that store's domain, our staff's link on our host."""
    from .models import TenantExport

    here = context.store_id()
    if here is not None and here != tenant_id:
        raise ExportError("link not found", "لینک پیدا نشد", 404, "not_found")
    scope = "store" if here is not None else "platform"
    h = _hash(token or "")
    now = timezone.now()
    with context.tenant_context(tenant_id):
        with transaction.atomic():
            e = (TenantExport.objects.select_for_update()
                 .filter(link_hash=h, link_scope=scope, state=TenantExport.READY, expires_at__gt=now, link_expires_at__gt=now)
                 .first())
            if e is not None:                                         # spent at once: the same link never works twice
                TenantExport.objects.filter(pk=e.pk).update(link_hash="", downloads=F("downloads") + 1, last_download_at=now)
                e.refresh_from_db()
        if e is None:
            raise ExportError("this link was already used or has expired — make a new one in the panel",
                              "این لینک قبلاً استفاده شده یا منقضی شده است — از پنل لینک تازه بگیرید", 410, "gone")
        write_audit(action="store.export_downloaded", target=e,
                    detail={"tenant": tenant_id, "export": e.pk, "scope": scope, "downloads": e.downloads})
    return e


# ------------------------------------------------------------------ cleanup (hourly, every store)
def _cleanup_store() -> dict:
    from .models import TenantExport

    now = timezone.now()
    expired = failed = 0
    for e in TenantExport.objects.filter(state=TenantExport.READY, expires_at__lte=now):
        _delete_file(e.file)
        TenantExport.objects.filter(pk=e.pk).update(state=TenantExport.EXPIRED, file="", link_hash="")
        expired += 1
    for e in TenantExport.objects.filter(state__in=(TenantExport.QUEUED, TenantExport.RUNNING), created_at__lte=now - STUCK):
        _delete_file(e.file)
        TenantExport.objects.filter(pk=e.pk).update(state=TenantExport.FAILED, error="timed out", finished_at=now)
        failed += 1
    return {"expired": expired, "failed": failed}


def cleanup() -> dict:
    out = context.for_each_tenant(_cleanup_store, name="export cleanup")
    return {tid: r for tid, r in out.items() if r != {"expired": 0, "failed": 0}}


# ------------------------------------------------------------------ rows for the panels
def row(e, *, platform: bool = False) -> dict:
    who = e.requested_by if (platform or not e.by_platform) else SUPPORT
    return {"id": e.id, "state": e.state, "progress": e.progress, "step": e.step, "size": e.size, "counts": e.counts,
            "created_at": e.created_at, "finished_at": e.finished_at, "expires_at": e.expires_at, "requested_by": who,
            "by_platform": e.by_platform, "downloads": e.downloads, "last_download_at": e.last_download_at,
            "error": e.error[:200] if e.state == e.FAILED else ""}


def status(*, platform: bool = False) -> dict:
    from .models import TenantExport

    t = _tenant()
    nxt = None if platform else next_allowed_at(t)
    rows = [row(e, platform=platform) for e in TenantExport.objects.all()[:20]]
    busy = any(r["state"] in (TenantExport.QUEUED, TenantExport.RUNNING) for r in rows)
    return {"allowed": bool(platform or t.export_allowed), "next_allowed_at": nxt, "busy": busy,
            "keep_hours": int(KEEP.total_seconds() // 3600), "gap_hours": int(STORE_GAP.total_seconds() // 3600),
            "datasets": [{"name": n, "fa": fa, "en": en} for n, _fn, (fa, en) in DATASETS], "results": rows}
