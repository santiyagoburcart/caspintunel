"""Store import engine (v1.56, docs/store-import.md) — our staff bring a reseller's customers from another bot into the
reseller's store. Everything runs INSIDE the store's tenant context; nothing on PasarGuard is ever changed.

  upload  (request)  the dump is checked to be a MySQL dump and kept under media/imports/<store>/ (0600, nginx 404s it)
  scan    (Celery)   parse it with the matching adapter + ONE read-only listing of PasarGuard → `preview` (counts, masked
                     rows, the plan map to choose) and `report` (every service / customer and what will happen to it)
  run     (Celery)   only with «ربات قبلی فروش را متوقف کرده است» ticked: a DB backup first, then customers → services
                     (linked only when PasarGuard says the store's reseller owns the account) → referrals → carried-over
                     credits (one-use codes; a balance above `review_above` only when confirmed) → paid history (read-only
                     notes, never revenue). Idempotent: `ImportRecord` (tenant, kind, source_key) is never made twice.
  undo    (request)  removes what this import created and nothing used since (an order, a payment, a ticket keeps a
                     customer / service; a used credit stays). PasarGuard is never touched.

No customer is messaged by an import; one summary alert goes to OUR staff when it finishes.
"""
from __future__ import annotations

import csv
import hashlib
import io
import logging
import os
import secrets
from collections import Counter
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.common.models import write_audit

from .. import context
from ..models import ImportRecord, StoreImport, Tenant
from . import ADAPTERS, detect
from . import dump as D

log = logging.getLogger("caspintunel")
MEDIA_DIR = "imports"
FILE_HOURS = 24
REVIEW_ABOVE = 1_000_000            # tomans: a carried-over balance above this is imported only when staff confirm it
CREDIT_DAYS = 180
TEST_MAX_DAYS = 1                   # a service sold for ≤ 1 day is the old bot's free test — never linked
BUSY = (StoreImport.UPLOADED, StoreImport.SCANNING, StoreImport.RUNNING)
GB = 1024 ** 3

# what happens to one source service (report + preview counts)
OUTCOMES = {
    "link": ("وصل می‌شود", "will be linked"),
    "linked": ("وصل شد", "linked"),
    "test": ("سرویس تست (۱ روزه) — رد شد", "1-day test service — skipped"),
    "not_sold": ("پرداخت/تحویل نشده در ربات قبلی — رد شد", "never paid / delivered in the old bot — skipped"),
    "missing": ("در پاسارگارد پیدا نشد", "not found on PasarGuard"),
    "other_admin": ("متعلق به ادمین دیگری در پاسارگارد — وصل نمی‌شود", "owned by another PasarGuard admin — never linked"),
    "linked_elsewhere": ("قبلاً به مشتری دیگری وصل است", "already linked to another customer"),
    "no_customer": ("مشتری آن در فایل نیست", "its customer is not in the file"),
    "duplicate": ("تکراری (ردیف جدیدتر همین سرویس استفاده شد)", "duplicate (the newer row of this service is used)"),
    "already": ("قبلاً با همین ورود آمده", "already imported"),
    "failed": ("خطا هنگام وصل کردن", "failed to link"),
}


class ImportFailure(Exception):
    def __init__(self, en: str, fa: str, status: int = 400, code: str = "invalid"):
        super().__init__(en)
        self.en, self.fa, self.status, self.code = en, fa, status, code

    def payload(self) -> dict:
        return {"detail": self.en, "detail_fa": self.fa, "code": self.code}


# ------------------------------------------------------------------ helpers
def _store() -> Tenant:
    tid = context.current_tenant_id()
    t = Tenant.objects.filter(pk=tid).first() if tid else None
    if t is None or t.is_default:
        raise ImportFailure("imports are only for reseller stores", "ورود داده فقط برای فروشگاه نمایندگان است", 404, "no_store")
    if not t.reseller_username:
        raise ImportFailure("this store has no PasarGuard admin", "این فروشگاه ادمین پاسارگارد ندارد", 409, "no_reseller")
    return t


def mask(v, keep: int = 2) -> str:
    v = str(v or "")
    if not v:
        return ""
    return v[:keep] + "•" * min(6, max(2, len(v) - keep))


def _path(obj: StoreImport) -> Path:
    return Path(settings.MEDIA_ROOT) / obj.file


def _staff_name(staff) -> str:
    return getattr(staff, "username", "") or "system"


def _load(obj: StoreImport):
    if not obj.file or not _path(obj).exists():
        raise ImportFailure("the uploaded file is gone (kept 24 h) — upload it again",
                            "فایل بارگذاری‌شده دیگر نیست (۲۴ ساعت نگه داشته می‌شود) — دوباره بارگذاری کنید", 410, "file_gone")
    tables = D.parse(_path(obj).read_text(encoding="utf-8", errors="replace"))
    adapter = ADAPTERS.get(obj.source) or detect(tables)
    if adapter is None:
        raise ImportFailure("unknown source: this dump is not from a supported bot",
                            "این فایل از رباتی که پشتیبانی می‌شود نیست (فعلاً: ربات میرزا)", 400, "unknown_source")
    return adapter, adapter.parse(tables)


def _delete_file(obj: StoreImport) -> None:
    if obj.file:
        try:
            _path(obj).unlink(missing_ok=True)
        except OSError as exc:      # never fail an import over a leftover file; cleanup retries
            log.warning("store import %s: could not delete %s: %s", obj.pk, obj.file, exc)
            return
        obj.file = ""


# ------------------------------------------------------------------ upload
def upload(raw: bytes, name: str, *, staff=None) -> StoreImport:
    t = _store()
    if StoreImport.objects.filter(state__in=BUSY).exists():
        raise ImportFailure("another import of this store is in progress", "یک ورود دیگر برای این فروشگاه در جریان است", 409, "busy")
    try:
        text = D.read_upload(raw, name)
    except D.DumpError as exc:
        raise ImportFailure(exc.en, exc.fa, 400, "bad_file") from exc
    rel = f"{MEDIA_DIR}/{t.pk}/{secrets.token_urlsafe(24)}.sql"
    full = Path(settings.MEDIA_ROOT) / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(full.parent, 0o700)
    fd = os.open(full, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    obj = StoreImport.objects.create(
        file=rel, file_name=os.path.basename(name or "dump.sql")[:150], size=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(), reseller=t.reseller_username, created_by=_staff_name(staff),
        file_expires_at=timezone.now() + timedelta(hours=FILE_HOURS))
    write_audit(action="store.import_uploaded", staff=staff, target=obj, detail={"store": t.pk, "size": len(raw)})
    _queue("scan_import_task", obj.pk, t.pk)
    return obj


def _queue(task: str, import_id: int, tenant_id: int) -> None:
    """After commit, queue the task INSIDE the store (celery_ctx stamps the tenant) — the request may have left the
    store's context by then."""
    def go():
        from .. import tasks

        with context.tenant_context(tenant_id):
            getattr(tasks, task).delay(import_id)
    transaction.on_commit(go)


# ------------------------------------------------------------------ PasarGuard (read-only) + our services
def _panel():
    from ..catalog import store_panel

    return store_panel()


def panel_accounts(panel, names: set[str]) -> dict[str, dict]:
    """{lower name: {username, owner, status}} for the names that exist on PasarGuard — ONE paged listing, read-only."""
    from apps.panel.services import client_for, panel_owner

    c, out, off = client_for(panel), {}, 0
    while True:
        users, total = c.list_users(limit=500, offset=off)
        for u in users:
            n = (u.get("username") or "").lower()
            if n in names:
                out[n] = {"username": u.get("username"), "owner": panel_owner(u), "status": u.get("status"), "raw": u}
        off += len(users)
        if not users or off >= total:
            return out


def linked_anywhere(panel, names: set[str]) -> dict[str, int]:
    """{lower name: tenant id} for accounts already linked to a service in ANY store (ours included) — one store at a time,
    inside its own context (no unscoped queries)."""
    from apps.panel.models import Service

    found = {}
    lowered = sorted(names)
    for tid in Tenant.objects.values_list("pk", flat=True):
        with context.tenant_context(tid):
            for i in range(0, len(lowered), 500):
                for n in Service.objects.filter(panel=panel, panel_username__in=lowered[i:i + 500]).values_list("panel_username", flat=True):
                    found[n.lower()] = tid
    return found


# ------------------------------------------------------------------ the plan (preview + report)
def _store_plans(panel) -> list[dict]:
    from apps.plans.models import Plan

    return [{"id": p.id, "name": p.name_fa, "gb": (p.data_limit or 0) // GB if p.data_limit else None, "days": p.duration_days,
             "price": int(p.price), "vpn_type": p.vpn_type, "active": p.is_active}
            for p in Plan.objects.filter(panel=panel).order_by("-is_active", "sort_order", "id")]


def _suggest(group: dict, plans: list[dict]) -> int | None:
    same = [p for p in plans if p["active"] and p["gb"] == group["gb"] and p["days"] == group["days"]]
    if group.get("wireguard"):
        same.sort(key=lambda p: p["vpn_type"] not in ("wireguard", "both"))
    return same[0]["id"] if same else None


def plan(src, *, store: Tenant, panel, accounts: dict, linked: dict, done_keys: set, review_above: int) -> tuple[dict, list]:
    """What an import of `src` would do now. Pure (no writes): the preview and the report rows."""
    from apps.accounts.models import User

    customers = {c.key: c for c in src.customers}
    existing_tg = set(User.objects.filter(telegram_id__in=[c.telegram_id for c in src.customers]).values_list("telegram_id", flat=True))
    reseller = store.reseller_username.lower()
    report, svc_counts, live_missing = [], Counter(), []

    # newest row per account name wins
    latest: dict[str, object] = {}
    for s in src.services:
        n = s.panel_username.lower()
        if n and (n not in latest or (s.sold_at or timezone.now()) >= (latest[n].sold_at or timezone.now())):
            latest[n] = s
    groups: dict[str, dict] = {}
    for s in src.services:
        n = s.panel_username.lower()
        acc = accounts.get(n)
        if not n or latest.get(n) is not s:
            out = "duplicate"
        elif ("service", s.key) in done_keys:
            out = "already"
        elif not s.sold:
            out = "not_sold"
        elif s.days <= TEST_MAX_DAYS:
            out = "test"
        elif acc is None:
            out = "missing"
        elif acc["owner"].lower() != reseller:
            out = "other_admin"
        elif n in linked:
            out = "linked_elsewhere"
        elif s.customer_key not in customers:
            out = "no_customer"
        else:
            out = "link"
        svc_counts[out] += 1
        cust = customers.get(s.customer_key)
        row = {"type": "service", "key": s.key, "panel_username": s.panel_username, "bot_status": s.status,
               "product": s.product_name, "gb": s.volume_gb, "days": s.days, "sold_at": s.sold_at.isoformat() if s.sold_at else "",
               "customer": cust.telegram_username if cust else "", "customer_id": cust.telegram_id if cust else "",
               "panel_status": acc["status"] if acc else "", "panel_owner": (acc["owner"] if acc and out != "other_admin" else ""),
               "outcome": out, "live_in_bot": s.live}
        report.append(row)
        if out == "missing" and s.live:
            live_missing.append({k: row[k] for k in ("panel_username", "bot_status", "product", "gb", "days", "sold_at")})
        if out == "link":
            name = s.product_name or "—"
            g = groups.setdefault(name, {"name": name, "count": 0, "gb": s.volume_gb, "days": s.days,
                                         "wireguard": "wireguard" in (s.location or "").lower()})
            g["count"] += 1
    plans = _store_plans(panel)
    for g in groups.values():
        g["suggested_plan"] = _suggest(g, plans)

    # customers
    cust_counts = Counter()
    for c in src.customers:
        cust_counts["existing" if c.telegram_id in existing_tg else "new"] += 1
        cust_counts["blocked"] += c.blocked
        cust_counts["agents"] += c.agent
        cust_counts["with_phone"] += bool(c.phone)
        cust_counts["referred"] += bool(c.referrer_key and c.referrer_key in customers)
        report.append({"type": "customer", "key": c.key, "customer": c.telegram_username, "customer_id": c.telegram_id,
                       "outcome": "existing" if c.telegram_id in existing_tg else ("already" if ("user", c.key) in done_keys else "new"),
                       "balance": c.balance, "blocked": c.blocked})
    # credits
    with_balance = [c for c in src.customers if c.balance > 0]
    review = [c for c in with_balance if c.balance > review_above]
    normal = [c for c in with_balance if c.balance <= review_above]
    paid = [p for p in src.payments if p.paid and p.customer_key in customers]
    from apps.settings_app.utils import get_setting

    preview = {
        "source": {"system": src.system, "label": src.label, "panels": src.panels},
        "store": {"id": store.pk, "name": store.name, "reseller": store.reseller_username,
                  "phone_required": bool(get_setting("force_share_phone", False)),
                  "iran_phone_only": bool(get_setting("iran_phone_only", False))},
        "customers": {"total": len(src.customers), **{k: cust_counts[k] for k in ("new", "existing", "blocked", "agents", "with_phone", "referred")}},
        "services": {"total": len(src.services), **{k: svc_counts[k] for k in OUTCOMES if k in svc_counts}},
        "outcomes": {k: {"fa": v[0], "en": v[1]} for k, v in OUTCOMES.items()},
        "missing_live": live_missing,
        "plan_groups": sorted(groups.values(), key=lambda g: -g["count"]),
        "plans": plans,
        "credits": {"count": len(normal), "total": sum(c.balance for c in normal), "review_above": review_above,
                    "review": [{"key": ckey(c), "who": mask(c.telegram_username or c.telegram_id, 2), "amount": c.balance}
                               for c in sorted(review, key=lambda c: -c.balance)]},
        "history": {"paid": len(paid), "total": sum(p.amount for p in paid),
                    "by_kind": dict(Counter(p.kind for p in paid))},
        "credit_days": CREDIT_DAYS,
    }
    return preview, report


def ckey(c) -> str:
    """A credit's id on the page (never the Telegram id itself)."""
    return hashlib.sha256(f"credit:{c.key}".encode()).hexdigest()[:12]


def _done_keys() -> set:
    return set(ImportRecord.objects.values_list("kind", "source_key"))


def scan(import_id: int) -> dict:
    """Celery (inside the store): parse + read-only PasarGuard listing → preview + report."""
    obj = StoreImport.objects.filter(pk=import_id).first()
    if obj is None or obj.state not in (StoreImport.UPLOADED, StoreImport.READY):
        return {"skipped": True}
    obj.state, obj.progress, obj.error = StoreImport.SCANNING, 10, ""
    obj.save(update_fields=["state", "progress", "error", "updated_at"])
    try:
        store = _store()
        adapter, src = _load(obj)
        obj.source = adapter.NAME
        panel = _panel()
        names = {s.panel_username.lower() for s in src.services if s.panel_username}
        accounts = panel_accounts(panel, names)
        obj.progress = 70
        obj.save(update_fields=["progress", "source", "updated_at"])
        preview, report = plan(src, store=store, panel=panel, accounts=accounts, linked=linked_anywhere(panel, names),
                               done_keys=_done_keys(), review_above=int(obj.options.get("review_above") or REVIEW_ABOVE))
    except ImportFailure as exc:
        return _fail(obj, exc.en)
    except Exception as exc:  # noqa: BLE001 — a bad file / panel outage ends as «ناموفق» with the reason, never a crash loop
        log.exception("store import %s scan failed", import_id)
        return _fail(obj, f"scan failed: {exc}")
    obj.preview, obj.report, obj.state, obj.progress = preview, report, StoreImport.READY, 100
    obj.save(update_fields=["preview", "report", "state", "progress", "source", "updated_at"])
    return {"ready": True}


def _fail(obj, why: str) -> dict:
    obj.state, obj.error, obj.finished_at = StoreImport.FAILED, str(why)[:500], timezone.now()
    obj.save(update_fields=["state", "error", "finished_at", "updated_at"])
    return {"failed": obj.error}


# ------------------------------------------------------------------ start + run
def start(import_id: int, data: dict, *, staff=None) -> StoreImport:
    """Checks the page's choices and queues the import. `data`: {old_bot_stopped: true, plan_map: {product name: plan id |
    null}, confirm_credits: [key], credit_days}."""
    from apps.plans.models import Plan

    store = _store()
    with transaction.atomic():
        obj = StoreImport.objects.select_for_update().filter(pk=import_id).first()
        if obj is None:
            raise ImportFailure("import not found", "ورود داده پیدا نشد", 404, "not_found")
        if obj.state != StoreImport.READY:
            raise ImportFailure("this import is not ready to run", "این ورود داده آمادهٔ اجرا نیست", 409, "not_ready")
        if data.get("old_bot_stopped") is not True:
            raise ImportFailure("tick «the old bot has stopped selling» first",
                                "اول تیک «ربات قبلی فروش را متوقف کرده است» را بزنید", 400, "old_bot")
        panel = _panel()
        valid = set(Plan.objects.filter(panel=panel).values_list("pk", flat=True))
        groups = {g["name"] for g in obj.preview.get("plan_groups", [])}
        plan_map = {}
        for name, pid in (data.get("plan_map") or {}).items():
            if name not in groups:
                continue
            if pid in (None, "", 0):
                plan_map[name] = None
            elif int(pid) in valid:
                plan_map[name] = int(pid)
            else:
                raise ImportFailure("a chosen plan is not a plan of this store", "پلن انتخاب‌شده از پلن‌های این فروشگاه نیست",
                                    400, "plan")
        review = {r["key"] for r in obj.preview.get("credits", {}).get("review", [])}
        confirm = [k for k in (data.get("confirm_credits") or []) if k in review]
        days = int(data.get("credit_days") or CREDIT_DAYS)
        if not 7 <= days <= 365:
            raise ImportFailure("credit validity: 7–365 days", "اعتبار کدها: ۷ تا ۳۶۵ روز", 400, "credit_days")
        obj.options = {**obj.options, "old_bot_stopped": True, "plan_map": plan_map, "confirm_credits": confirm,
                       "credit_days": days, "store": store.pk}
        obj.state, obj.progress, obj.run_by, obj.error = StoreImport.RUNNING, 0, _staff_name(staff), ""
        obj.save(update_fields=["options", "state", "progress", "run_by", "error", "updated_at"])
        write_audit(action="store.import_started", staff=staff, target=obj,
                    detail={"store": store.pk, "plans_mapped": sum(1 for v in plan_map.values() if v),
                            "credits_confirmed": len(confirm), "credit_days": days})
    _queue("run_import_task", obj.pk, store.pk)
    return obj


def run(import_id: int) -> dict:
    """Celery (inside the store): backup, then the import. Re-running after a failure continues where it stopped."""
    obj = StoreImport.objects.filter(pk=import_id).first()
    if obj is None or obj.state != StoreImport.RUNNING:
        return {"skipped": True}
    obj.started_at = timezone.now()
    obj.save(update_fields=["started_at", "updated_at"])
    try:
        store = _store()
        from apps.telegram.backup import run_database_backup

        b = run_database_backup()
        obj.backup_log_id = b.pk
        obj.save(update_fields=["backup_log_id", "updated_at"])
        if b.status != "ok":
            raise ImportFailure(f"the database backup before the import failed: {b.error}"[:400],
                                "پشتیبان‌گیری پیش از ورود داده ناموفق بود — چیزی وارد نشد", 500, "backup")
        adapter, src = _load(obj)
        result = _apply(obj, store, src)
    except ImportFailure as exc:
        return _fail(obj, exc.en)
    except Exception as exc:  # noqa: BLE001
        log.exception("store import %s failed", import_id)
        return _fail(obj, f"import failed: {exc}")
    obj.result, obj.state, obj.progress, obj.finished_at = result, StoreImport.DONE, 100, timezone.now()
    _delete_file(obj)
    obj.save(update_fields=["result", "state", "progress", "finished_at", "file", "updated_at"])
    write_audit(action="store.import_done", staff=None, target=obj, detail={"store": store.pk, **result})
    _alert_done(store, obj, result)
    return result


def _apply(obj: StoreImport, store: Tenant, src) -> dict:
    from apps.accounts.models import User
    from apps.panel.exceptions import PanelError
    from apps.panel.services import link_existing_service
    from apps.plans.models import Plan

    panel = _panel()
    names = {s.panel_username.lower() for s in src.services if s.panel_username}
    accounts = panel_accounts(panel, names)                       # fresh: ownership is checked again right now
    review_above = int(obj.options.get("review_above") or REVIEW_ABOVE)
    _, report = plan(src, store=store, panel=panel, accounts=accounts, linked=linked_anywhere(panel, names),
                     done_keys=_done_keys(), review_above=review_above)
    plan_map = obj.options.get("plan_map") or {}
    plans = {p.pk: p for p in Plan.objects.filter(pk__in=[v for v in plan_map.values() if v])}
    res = Counter()
    users: dict[str, User] = {}

    # 1) customers
    for i, c in enumerate(src.customers):
        users[c.key] = _customer(obj, c, res)
        if i % 50 == 0:
            StoreImport.objects.filter(pk=obj.pk).update(progress=5 + int(35 * i / max(1, len(src.customers))))
    # 2) services (only rows the fresh plan says "link")
    svc = {s.key: s for s in src.services}
    rows = [r for r in report if r["type"] == "service"]
    for i, r in enumerate(rows):
        if r["outcome"] != "link":
            continue
        s, u = svc[r["key"]], users.get(svc[r["key"]].customer_key)
        if u is None:
            r["outcome"] = "no_customer"
            continue
        try:
            with transaction.atomic():
                service = link_existing_service(
                    user=u, panel=panel, panel_username=s.panel_username, plan=plans.get(plan_map.get(s.product_name or "—")),
                    staff=None, owner_must_be=store.reseller_username, api_user=accounts[s.panel_username.lower()]["raw"],
                    source="import")
                ImportRecord.objects.create(batch=obj, kind=ImportRecord.SERVICE, source_key=s.key, user=u, object_id=service.pk,
                                            data={"panel_username": service.panel_username,
                                                  "order": service.orders.values_list("pk", flat=True).first()})
            r["outcome"] = "linked"
            res["services_linked"] += 1
        except (PanelError, ValueError) as exc:
            r["outcome"], r["error"] = "failed", str(exc)[:200]
            res["services_failed"] += 1
        if i % 20 == 0:
            StoreImport.objects.filter(pk=obj.pk).update(progress=40 + int(40 * i / max(1, len(rows))))
    # 3) referrals
    for c in src.customers:
        ref = users.get(c.referrer_key)
        u = users.get(c.key)
        if ref and u and ref.pk != u.pk and u.referred_by_id is None and not ImportRecord.objects.filter(
                kind=ImportRecord.REFERRAL, source_key=c.key).exists():
            User.objects.filter(pk=u.pk).update(referred_by=ref)
            ImportRecord.objects.create(batch=obj, kind=ImportRecord.REFERRAL, source_key=c.key, user=u, object_id=ref.pk)
            res["referrals"] += 1
    # 4) carried-over credits
    confirmed = set(obj.options.get("confirm_credits") or [])
    days = int(obj.options.get("credit_days") or CREDIT_DAYS)
    for c in src.customers:
        u = users.get(c.key)
        if not u or c.balance <= 0:
            continue
        if c.balance > review_above and ckey(c) not in confirmed:
            res["credits_held"] += 1
            continue
        if ImportRecord.objects.filter(kind=ImportRecord.CREDIT, source_key=c.key).exists():
            continue
        dc = _credit(obj, u, c.balance, days)
        ImportRecord.objects.create(batch=obj, kind=ImportRecord.CREDIT, source_key=c.key, user=u, object_id=dc.pk,
                                    data={"amount": c.balance, "code": dc.code})
        res["credits"] += 1
        res["credit_total"] += c.balance
    # 5) paid history (read-only notes)
    for p in src.payments:
        u = users.get(p.customer_key)
        if not p.paid or u is None or ImportRecord.objects.filter(kind=ImportRecord.HISTORY, source_key=p.key).exists():
            continue
        ImportRecord.objects.create(batch=obj, kind=ImportRecord.HISTORY, source_key=p.key, user=u, at=p.at,
                                    data={"amount": p.amount, "kind": p.kind, "method": p.method,
                                          "service": p.ref if p.ref.lower() in names else ""})
        res["history"] += 1
    StoreImport.objects.filter(pk=obj.pk).update(report=report, progress=99)
    obj.report = report
    return dict(res)


def _customer(obj, c, res):
    from apps.accounts.models import Source, User
    from apps.accounts.phone import normalize_ir_phone
    from apps.telegram.accounts import _unique_username

    u = User.objects.filter(telegram_id=c.telegram_id).first()
    if u is not None:
        if not ImportRecord.objects.filter(kind=ImportRecord.USER, source_key=c.key).exists():
            ImportRecord.objects.create(batch=obj, kind=ImportRecord.USER, source_key=c.key, user=u, object_id=u.pk, created=False)
        res["customers_existing"] += 1
        return u
    phone = normalize_ir_phone(c.phone) if c.phone else None
    if phone and User.objects.filter(phone=phone).exists():
        phone = None                          # the number already belongs to a customer of this store: never two accounts
    stamp = timezone.now().strftime("%Y-%m-%d %H:%M")
    with transaction.atomic():
        u = User.objects.create_user(
            username=_unique_username(), password=secrets.token_urlsafe(12), telegram_id=c.telegram_id,
            telegram_username=c.telegram_username, phone=phone or "", source=Source.BOT, language=c.language,
            is_active=not c.blocked,
            admin_note=f"[{stamp}] imported from the old bot (store import #{obj.pk})" + (" — blocked there" if c.blocked else ""))
        ImportRecord.objects.create(batch=obj, kind=ImportRecord.USER, source_key=c.key, user=u, object_id=u.pk)
    res["customers_created"] += 1
    return u


def _credit(obj, user, amount: int, days: int):
    from apps.crm.discounts import random_code
    from apps.crm.models import DiscountCode, DiscountKind, DiscountType

    return DiscountCode.objects.create(
        code=random_code("CR"), kind=DiscountKind.CREDIT, user=user, name="اعتبار ربات قبلی", discount_type=DiscountType.FIXED,
        amount_off=amount, max_uses=1, max_uses_per_customer=1, expires_at=timezone.now() + timedelta(days=days),
        note=f"store import #{obj.pk}", created_by="import")


def _alert_done(store, obj, result) -> None:
    try:
        from apps.common.staff_alert import alert_staff

        alert_staff(f"📥 ورود دادهٔ فروشگاه «{store.name}» تمام شد (#{obj.pk}): "
                    f"{result.get('customers_created', 0)} مشتری جدید، {result.get('services_linked', 0)} سرویس وصل شد، "
                    f"{result.get('credits', 0)} کد اعتبار، {result.get('history', 0)} سابقهٔ پرداخت.",
                    perm="agency.manage", platform=True, silent=True)
    except Exception as exc:  # noqa: BLE001 — an alert outage never fails the import
        log.warning("store import alert failed: %s", exc)


# ------------------------------------------------------------------ undo
def undo(import_id: int, *, staff=None) -> dict:
    """Remove what this import made and nothing used since. PasarGuard is never touched."""
    from apps.accounts.models import User
    from apps.crm.discounts import held_orders
    from apps.crm.models import DiscountCode
    from apps.orders.models import Order
    from apps.panel.models import Service

    _store()
    with transaction.atomic():
        obj = StoreImport.objects.select_for_update().filter(pk=import_id).first()
        if obj is None:
            raise ImportFailure("import not found", "ورود داده پیدا نشد", 404, "not_found")
        if obj.state not in (StoreImport.DONE, StoreImport.FAILED) or not obj.records.exists():
            raise ImportFailure("nothing to undo", "چیزی برای بازگردانی نیست", 409, "nothing")
        out, kept = Counter(), []
        recs = obj.records.all()
        for r in recs.filter(kind=ImportRecord.CREDIT):
            dc = DiscountCode.objects.filter(pk=r.object_id).first()
            if dc is not None and (dc.used_at or dc.order_id or held_orders(dc).exists()):
                kept.append({"kind": "credit", "id": dc.pk, "why": "used"})
                continue
            if dc is not None:
                dc.delete()
            r.delete()
            out["credits"] += 1
        out["history"] = recs.filter(kind=ImportRecord.HISTORY).delete()[0]
        for r in recs.filter(kind=ImportRecord.REFERRAL):
            User.objects.filter(pk=r.user_id, referred_by_id=r.object_id).update(referred_by=None)
            r.delete()
            out["referrals"] += 1
        for r in recs.filter(kind=ImportRecord.SERVICE):
            s = Service.objects.filter(pk=r.object_id).first()
            own_order = (r.data or {}).get("order")
            if s is not None and Order.objects.filter(service=s).exclude(pk=own_order).exists():
                kept.append({"kind": "service", "id": s.pk, "why": "has orders since"})
                continue
            if own_order:
                Order.objects.filter(pk=own_order, type="imported", amount=0).delete()
            if s is not None:
                s.delete()                                    # our row only — nothing is sent to PasarGuard
            r.delete()
            out["services"] += 1
        for r in recs.filter(kind=ImportRecord.USER):
            if not r.created:
                r.delete()
                continue
            u = User.objects.filter(pk=r.object_id).first()
            if u is not None and (Order.objects.filter(user=u).exists() or u.services.exists()
                                  or u.tickets.exists() or ImportRecord.objects.filter(user=u).exclude(pk=r.pk).exists()):
                kept.append({"kind": "customer", "id": u.pk, "why": "has activity since"})
                continue
            if u is not None:
                u.delete()
            r.delete()
            out["customers"] += 1
        obj.state, obj.undone_at = StoreImport.UNDONE, timezone.now()
        obj.result = {**obj.result, "undo": dict(out), "kept": kept}
        obj.save(update_fields=["state", "undone_at", "result", "updated_at"])
        write_audit(action="store.import_undone", staff=staff, target=obj, detail={"removed": dict(out), "kept": len(kept)})
    return {"removed": dict(out), "kept": kept}


def discard(import_id: int, *, staff=None) -> None:
    _store()
    obj = StoreImport.objects.filter(pk=import_id).first()
    if obj is None:
        raise ImportFailure("import not found", "ورود داده پیدا نشد", 404, "not_found")
    if obj.state in (StoreImport.RUNNING, StoreImport.SCANNING, StoreImport.DONE):
        raise ImportFailure("this import cannot be discarded now", "این ورود داده الان قابل حذف نیست", 409, "busy")
    _delete_file(obj)
    obj.state = StoreImport.DISCARDED if obj.state != StoreImport.UNDONE else obj.state
    obj.save(update_fields=["file", "state", "updated_at"])
    write_audit(action="store.import_discarded", staff=staff, target=obj, detail={})


def cleanup() -> dict:
    """Hourly (every store): delete dumps 24 h after upload; fail scans / runs stuck for 2 h."""
    out = context.for_each_tenant(_cleanup_store, name="import cleanup")
    return {tid: r for tid, r in out.items() if r}


def _cleanup_store() -> dict:
    now, out = timezone.now(), Counter()
    for obj in StoreImport.objects.exclude(file="").filter(file_expires_at__lte=now).exclude(state=StoreImport.RUNNING):
        _delete_file(obj)
        if obj.state in (StoreImport.UPLOADED, StoreImport.READY):
            obj.state = StoreImport.DISCARDED
        obj.save(update_fields=["file", "state", "updated_at"])
        out["files"] += 1
    stuck = StoreImport.objects.filter(state__in=BUSY, updated_at__lte=now - timedelta(hours=2))
    for obj in stuck:
        _fail(obj, "stopped (no progress for 2 hours)")
        out["stuck"] += 1
    return dict(out)


# ------------------------------------------------------------------ page + CSV
def row(obj: StoreImport, *, full: bool = False) -> dict:
    d = {"id": obj.id, "state": obj.state, "source": obj.source, "file_name": obj.file_name, "size": obj.size,
         "progress": obj.progress, "error": obj.error, "created_by": obj.created_by, "run_by": obj.run_by,
         "created_at": obj.created_at, "started_at": obj.started_at, "finished_at": obj.finished_at, "undone_at": obj.undone_at,
         "file_kept": bool(obj.file), "file_expires_at": obj.file_expires_at, "result": obj.result,
         "can_undo": obj.state in (StoreImport.DONE, StoreImport.FAILED) and obj.records.exists()}
    if full:
        d["preview"], d["options"] = obj.preview, obj.options
    return d


def status() -> dict:
    _store()
    rows = list(StoreImport.objects.all()[:10])
    return {"results": [row(o, full=(i == 0)) for i, o in enumerate(rows)],
            "busy": any(o.state in BUSY for o in rows)}


REPORT_COLS = ("type", "outcome", "outcome_fa", "panel_username", "bot_status", "live_in_bot", "panel_status", "panel_owner",
               "product", "gb", "days", "sold_at", "customer", "customer_id", "balance", "blocked", "error")


def report_csv(import_id: int) -> tuple[str, bytes]:
    _store()
    obj = StoreImport.objects.filter(pk=import_id).first()
    if obj is None or not obj.report:
        raise ImportFailure("no report yet", "هنوز گزارشی نیست", 404, "not_found")
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=REPORT_COLS, extrasaction="ignore")
    w.writeheader()
    order = {"missing": 0, "other_admin": 1, "failed": 2}
    for r in sorted(obj.report, key=lambda r: (r["type"] != "service", order.get(r["outcome"], 9), not r.get("live_in_bot"))):
        fa = OUTCOMES.get(r["outcome"], ("", ""))[0] if r["type"] == "service" else {
            "new": "مشتری جدید", "existing": "از قبل در فروشگاه", "already": "قبلاً آمده"}.get(r["outcome"], "")
        w.writerow({**r, "outcome_fa": fa})
    return f"store-import-{obj.pk}-report.csv", ("﻿" + buf.getvalue()).encode("utf-8")
