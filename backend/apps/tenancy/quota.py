"""Reseller quota guard + warnings for store sales (multi-tenant Phase 4, docs/multi-tenant.md §10, decision D6).

A store's services are owned by the reseller's PasarGuard admin (`set_owner`), so they use the reseller's quota. Before
a store sells — new service, renewal, add-on, manual invoice with a service action — and again right before the account
is created, `check()` compares the volume asked for with what the reseller has left:

    available = remaining − volumes of the store's open orders (waiting for payment inside the reservation, paid but not
                delivered) − paid renewals not applied yet

`remaining` is the EXISTING agency number enforcement uses (`PanelAdmin.admin_remaining` = limit − the reseller users'
traffic, synced every 2 min). When this sale would leave less than 10 % of the limit, the same number is recomputed live
(`panel_api.get_admin_user_stats`, the sync's own formula, cached 60 s). Not enough → the sale is refused with a friendly
message (no order), the reseller gets a portal notice and we get a staff alert. Unlimited reseller admins are never
blocked; an unlimited plan in a limited reseller's store is refused (its volume cannot be reserved).

Warnings (`warn_all`, every 5 min): 20 % and 10 % remaining → portal notice to the reseller + staff alert, once per level
(`Tenant.quota_alert_level`, reset when quota is raised again); the store dashboard shows a banner (`state()`).
Our own store (the default tenant) is never checked.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.core.cache import cache
from django.utils import timezone

from . import context

log = logging.getLogger("caspintunel")

GB = 1024 ** 3
WARN_LEVELS = (20, 10)          # % remaining (= 80 % / 90 % used)
LIVE_MARGIN = Decimal("0.10")   # recompute live when a sale would leave less than 10 % of the limit
LIVE_TTL = 60


class QuotaShort(Exception):
    """A store sale the reseller's quota cannot cover. `message(lang)` is what the customer sees."""

    code = "quota"

    def __init__(self, en: str, fa: str, *, detail: dict | None = None):
        super().__init__(en)
        self.en, self.fa, self.detail = en, fa, detail or {}

    def message(self, lang: str = "fa") -> str:
        return self.en if lang == "en" else self.fa


CUSTOMER_FA = "این خرید فعلاً در دسترس نیست — لطفاً کمی بعد دوباره تلاش کنید یا با پشتیبانی تماس بگیرید."
CUSTOMER_EN = "This purchase is temporarily unavailable — please try again a little later or contact support."


# ------------------------------------------------------------------ numbers
def _store(tenant_id):
    from .models import Tenant

    t = Tenant.objects.filter(pk=tenant_id).first() if tenant_id else None
    return None if t is None or t.is_default else t


def reseller_of(tenant):
    from apps.agency.models import PanelAdmin

    if tenant is None or not tenant.reseller_username:
        return None
    return PanelAdmin.objects.filter(username__iexact=tenant.reseller_username).first()


def limited(pa) -> bool:
    return bool(pa is not None and pa.has_data_limit and (pa.admin_limit_bytes or 0) > 0)


def plan_bytes(plan, custom_gb: int | None = None) -> int | None:
    """The volume a purchase of `plan` asks for; None = unlimited."""
    from apps.plans.models import PlanType

    if plan.type == PlanType.CUSTOM_VOLUME:
        return int(custom_gb or 0) * GB
    return int(plan.data_limit) if plan.data_limit else None


def order_bytes(order) -> int:
    return plan_bytes(order.plan, order.custom_volume_gb) or 0


def reserved_bytes(*, exclude_order: int | None = None) -> int:
    """Open volume of the CURRENT store: orders waiting inside their reservation or paid but not delivered, and paid
    renewals not applied yet."""
    from apps.orders.models import Order, OrderStatus, ScheduledRenewal

    now = timezone.now()
    total = 0
    qs = (Order.objects.filter(status__in=(OrderStatus.PENDING_PAYMENT, OrderStatus.PAID)).select_related("plan")
          .exclude(status=OrderStatus.PENDING_PAYMENT, unique_expire_at__lt=now))
    if exclude_order:
        qs = qs.exclude(pk=exclude_order)
    for o in qs:
        total += order_bytes(o)
    for sr in ScheduledRenewal.objects.filter(applied_at__isnull=True).select_related("plan"):
        total += int(sr.data_limit or 0) or int(getattr(sr.plan, "data_limit", 0) or 0)
    return total


def _live_remaining(pa) -> int | None:
    """limit − the reseller users' traffic, fetched now (the agency sync's own formula); None when the panel fails."""
    key = f"tenancy:quota:live:{pa.username.lower()}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    try:
        from apps.agency.panel_api import get_client

        used = int(get_client().get_admin_user_stats(pa.username)["total_user_used"] or 0)
    except Exception as exc:  # noqa: BLE001 — fall back to the synced number
        log.warning("quota: live usage of %s failed: %s", pa.username, exc)
        return None
    val = max(0, int(pa.admin_limit_bytes) - used)
    cache.set(key, val, LIVE_TTL)
    return val


def state(tenant_id: int | None = None, *, exclude_order: int | None = None, live: bool = False) -> dict | None:
    """The current store's quota picture (None for our own store)."""
    tid = tenant_id or context.current_tenant_id()
    t = _store(tid)
    if t is None:
        return None
    pa = reseller_of(t)
    out = {"reseller": t.reseller_username, "found": pa is not None, "limited": limited(pa)}
    if not out["limited"]:
        return out
    limit = int(pa.admin_limit_bytes)
    remaining = int(pa.admin_remaining or 0)
    source = "sync"
    if live:
        lv = _live_remaining(pa)
        if lv is not None:
            remaining, source = lv, "live"
    with context.tenant_context(t.pk):
        reserved = reserved_bytes(exclude_order=exclude_order)
    available = remaining - reserved
    out.update(limit=limit, remaining=remaining, reserved=reserved, available=available, source=source,
               synced_at=pa.last_synced_at, percent_remaining=round(max(0, available) * 100 / limit, 1) if limit else 0)
    return out


# ------------------------------------------------------------------ the guard
def check(need: int | None, *, exclude_order: int | None = None, what: str = "sale", alert: bool = True) -> dict | None:
    """Raise QuotaShort when the current store's reseller cannot cover `need` bytes (None = unlimited). No-op for our store."""
    tid = context.current_tenant_id()
    t = _store(tid)
    if t is None:
        return None
    pa = reseller_of(t)
    if pa is None:
        raise QuotaShort(f"store {t.slug}: reseller admin {t.reseller_username!r} not found", CUSTOMER_FA,
                         detail={"why": "no_reseller"})
    if not limited(pa):
        return None
    if need is None:
        raise QuotaShort("an unlimited plan cannot be sold under a limited reseller", CUSTOMER_FA,
                         detail={"why": "unlimited_plan"})
    st = state(t.pk, exclude_order=exclude_order)
    if st["available"] - need < LIVE_MARGIN * st["limit"]:
        st = state(t.pk, exclude_order=exclude_order, live=True)
    if st["available"] < need:
        if alert:
            _short_alert(t, st, need, what)
        raise QuotaShort(f"reseller quota short: {need} bytes asked, {max(0, st['available'])} available", CUSTOMER_FA,
                         detail={"why": "short", "need": need, **{k: st[k] for k in ("available", "remaining", "reserved")}})
    return st


def check_order(order, *, what: str = "provision") -> dict | None:
    """Right before the account is created / topped up (the order itself is not counted twice)."""
    return check(plan_bytes(order.plan, order.custom_volume_gb), exclude_order=order.pk, what=what)


def _gb(n) -> str:
    return f"{Decimal(max(0, int(n))) / GB:.1f}"


def _short_alert(t, st, need, what) -> None:
    from apps.agency.billing import notice
    from apps.common.staff_alert import alert_staff

    key = f"tenancy:quota:short:{t.pk}"
    if not cache.add(key, 1, 3600):
        return
    try:
        notice(admin=t.reseller_username, kind="quota_short",
               title="فروش فروشگاه به خاطر حجم ناکافی متوقف شد", title_en="Store sale blocked: not enough quota",
               body=f"باقی‌ماندهٔ قابل فروش {_gb(st['available'])} گیگ، درخواست {_gb(need)} گیگ — «درخواست شارژ» بزنید.",
               body_en=f"Available {_gb(st['available'])} GB, asked {_gb(need)} GB — send a volume request.")
    except Exception:  # noqa: BLE001
        log.exception("quota: reseller notice failed")
    alert_staff(f"⚠️ فروشگاه {t.name} ({t.reseller_username}): {what} به خاطر حجم ناکافی متوقف شد — باقی {_gb(st['available'])} گیگ، "
                f"درخواست {_gb(need)} گیگ.\nStore {t.slug}: {what} blocked, {_gb(st['available'])} GB available, {_gb(need)} GB asked.",
                perm="agency.manage", platform=True, dedupe_key=key + ":staff", ttl=3600)


# ------------------------------------------------------------------ warnings (every 5 min)
def level_for(percent_remaining: float) -> int:
    for lv in sorted(WARN_LEVELS):
        if percent_remaining <= lv:
            return lv
    return 0


def warn_all() -> dict:
    from apps.agency.billing import notice
    from apps.common.staff_alert import alert_staff

    from .models import Tenant

    sent = {}
    for t in Tenant.objects.filter(is_default=False).exclude(status=Tenant.CLOSED):
        try:
            st = state(t.pk)
            if not st or not st.get("limited"):
                lv = 0
            else:
                lv = level_for(st["percent_remaining"])
            if lv == t.quota_alert_level:
                continue
            if lv and (t.quota_alert_level == 0 or lv < t.quota_alert_level):
                pct = st["percent_remaining"]
                notice(admin=t.reseller_username, kind="quota_low",
                       title=f"حجم فروشگاه رو به اتمام است ({pct}% باقی‌مانده)", title_en=f"Store quota running low ({pct}% left)",
                       body=f"باقی‌ماندهٔ قابل فروش {_gb(st['available'])} گیگ از {_gb(st['limit'])} گیگ — برای ادامهٔ فروش «درخواست شارژ» بزنید.",
                       body_en=f"{_gb(st['available'])} GB of {_gb(st['limit'])} GB left to sell — send a volume request to keep selling.")
                alert_staff(f"🔔 فروشگاه {t.name} ({t.reseller_username}): فقط {pct}% حجم باقی مانده ({_gb(st['available'])} گیگ).\n"
                            f"Store {t.slug}: {pct}% quota left.", perm="agency.manage", platform=True, silent=lv == 20,
                            dedupe_key=f"tenancy:quota:warn:{t.pk}:{lv}", ttl=6 * 3600)
                sent[t.slug] = lv
            Tenant.objects.filter(pk=t.pk).update(quota_alert_level=lv)
        except Exception:  # noqa: BLE001 — one store never stops the others
            log.exception("quota warning failed for store %s", t.slug)
    return {"warned": sent}
