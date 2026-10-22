"""Retention: pre-expiry warnings and the win-back queue (Phase 4).

Warnings (`run_warnings`, every 30 min — replaces the old fixed volume / expiry alert):
  rules = WarningRule rows (defaults data 80 % · 95 %, time 3 days · 1 day), each with
  its own fa / en message. A warning is stored per (service, kind, threshold, period)
  — the period key changes when the service is renewed — so every threshold goes out
  once per period. Channels are recorded one by one: the site bell goes out at once;
  bot and email wait for the end of the quiet hours (Tehran time) and a retry only
  sends a channel that is still missing. Every message carries a one-click renew:
  site/email link `/renew/<service>`, bot button `s:<service>:rn`.
  When the service is renewed (or a new one bought) within retention_conversion_days
  of a warning, the warning is marked converted (`renewed_at`).

Win-back (`run_winback`, hourly with the CRM task):
  a service seen expired / used up gets a ServiceEndMark; after retention_grace_hours
  without becoming live again — and when the customer has no other live service — a
  `winback` FollowUpCase opens. When the customer is live again within
  retention_winback_days the case closes itself as won_back with the money recovered
  (approved payments since the case opened); otherwise staff mark it lost with a reason.
  Optional first win-back message after the grace period (off by default).
"""
from __future__ import annotations

import html
import logging
import secrets
from datetime import datetime, time, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.settings_app.utils import get_setting

from .models import (
    CaseKind,
    CaseStatus,
    Category,
    DiscountCode,
    EventKind,
    FollowUpCase,
    MessageTemplate,
    Outcome,
    ServiceEndMark,
    ServiceWarning,
    WarningKind,
    WarningRule,
)

log = logging.getLogger("caspintunel")
GB = 1024 ** 3
TZ = ZoneInfo("Asia/Tehran")
LIVE = ("active", "on_hold")
ENDED = ("expired", "limited")

INT_SETTINGS = [
    ("retention_grace_hours", 24, 0, 720),
    ("retention_winback_days", 14, 1, 180),
    ("retention_conversion_days", 7, 1, 60),
    ("retention_discount_percent", 10, 1, 90),
    ("retention_discount_days", 7, 1, 90),
    ("retention_auto_winback_template", 0, 0, 1_000_000),
]
BOOL_SETTINGS = [("retention_warnings_enabled", True), ("retention_auto_winback", False)]
STR_SETTINGS = [("retention_quiet_start", "00:00"), ("retention_quiet_end", "08:00")]


class RetentionError(ValueError):
    def __init__(self, message, code="invalid", status=400):
        super().__init__(message)
        self.code, self.status = code, status


def setting(key):
    for k, d, lo, hi in INT_SETTINGS:
        if k == key:
            try:
                return max(lo, min(hi, int(get_setting(k, d))))
            except (TypeError, ValueError):
                return d
    for k, d in BOOL_SETTINGS:
        if k == key:
            v = get_setting(k, d)
            return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on")
    for k, d in STR_SETTINGS:
        if k == key:
            return str(get_setting(k, d) or "")
    raise KeyError(key)


def all_settings() -> dict:
    keys = [k for k, *_ in INT_SETTINGS] + [k for k, _ in BOOL_SETTINGS] + [k for k, _ in STR_SETTINGS]
    return {k: setting(k) for k in keys}


def _hm(v: str):
    try:
        h, m = v.split(":")
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        return None


def quiet_until(now=None):
    """None when outside quiet hours, else the moment (UTC) they end. Off when start == end or unset."""
    now = now or timezone.now()
    start, end = _hm(setting("retention_quiet_start")), _hm(setting("retention_quiet_end"))
    if start is None or end is None or start == end:
        return None
    local = now.astimezone(TZ)
    t = local.time()
    inside = (start <= t < end) if start < end else (t >= start or t < end)
    if not inside:
        return None
    end_day = local.date() if t < end else local.date() + timedelta(days=1)
    return datetime.combine(end_day, end, tzinfo=TZ).astimezone(dt_timezone.utc)


def site_url() -> str:
    from apps.settings_app.models import SiteConfig

    d = (SiteConfig.load().site_domain or "").strip().strip("/")
    return f"https://{d}" if d else ""


def renew_path(service) -> str:
    return f"/renew/{service.id}"


def period_key(service) -> str:
    """Changes when the service is renewed / topped up: new expiry or new volume."""
    exp = service.expire_at.strftime("%Y%m%d%H") if service.expire_at else "noexp"
    return f"{exp}:{int(service.data_limit or 0)}"


# --- warnings --------------------------------------------------------------------------
def _due(service, rule, now) -> bool:
    if rule.kind == WarningKind.DATA:
        return bool(service.data_limit) and service.data_used >= service.data_limit * rule.threshold / 100
    if service.expire_at is None or service.expire_at <= now:
        return False
    return service.expire_at - now <= timedelta(days=rule.threshold)


def _render(text, service, now) -> str:
    u = service.user
    rem_gb = max(0, (service.data_limit or 0) - service.data_used) / GB if service.data_limit else None
    rem_days = max(0, (service.expire_at - now).days) if service.expire_at else None
    vals = {"name": u.name or u.username, "service": service.panel_username,
            "remaining_gb": f"{rem_gb:.1f}" if rem_gb is not None else "∞",
            "remaining_days": str(rem_days) if rem_days is not None else "∞",
            "renew": site_url() + renew_path(service)}

    class _Safe(dict):
        def __missing__(self, k):
            return "{" + k + "}"

    return (text or "").format_map(_Safe(vals))


def run_warnings() -> dict:
    """Create due warnings (only the strongest due threshold per kind; weaker ones of the same
    period are recorded as skipped) and deliver every channel that is still missing."""
    if not setting("retention_warnings_enabled"):
        return {"skipped": "disabled"}
    from apps.panel.models import Service

    now = timezone.now()
    rules = list(WarningRule.objects.filter(is_active=True))
    created = 0
    for s in Service.objects.filter(status="active", user__deleted_at__isnull=True).select_related("user"):
        key = period_key(s)
        for kind in (WarningKind.DATA, WarningKind.TIME):
            # data: highest % first; time: fewest days first — send only the most urgent due one
            krules = sorted((r for r in rules if r.kind == kind), key=lambda r: -r.threshold if kind == WarningKind.DATA else r.threshold)
            due = [r for r in krules if _due(s, r, now)]
            if not due:
                continue
            top = due[0]
            for r in due:
                try:
                    with transaction.atomic():
                        w = ServiceWarning.objects.create(service=s, rule=r, kind=kind, threshold=r.threshold, period_key=key,
                                                          due_at=now)
                except IntegrityError:
                    continue                              # already sent this period
                if r is not top:                          # passed while a stronger one is due: record, don't spam
                    w.site_sent_at = w.bot_sent_at = w.email_sent_at = now
                    w.bot_error = w.email_error = "skipped: a more urgent warning was due"
                    w.save()
                    continue
                created += 1
    delivered = deliver_pending(now)
    converted = mark_conversions(now)
    return {"created": created, **delivered, "converted": converted}


def deliver_pending(now=None) -> dict:
    from apps.notifications.dispatch import _deliver_email, _deliver_site
    from apps.notifications.models import DeliveryChannel, DeliveryStatus, Notification, NotificationDelivery, NotificationType

    now = now or timezone.now()
    quiet = quiet_until(now)
    out = {"site": 0, "bot": 0, "email": 0}
    pending = ServiceWarning.objects.filter(created_at__gte=now - timedelta(days=3)).select_related("service__user", "rule")
    for w in pending.filter(site_sent_at__isnull=True) | pending.filter(bot_sent_at__isnull=True) | pending.filter(email_sent_at__isnull=True):
        s, u, rule = w.service, w.service.user, w.rule
        if rule is None or u.deleted_at:
            continue
        title_fa, title_en = _render(rule.title_fa, s, now), _render(rule.title_en or rule.title_fa, s, now)
        body_fa, body_en = _render(rule.body_fa, s, now), _render(rule.body_en or rule.body_fa, s, now)
        if w.notification_id is None:
            note = Notification.objects.create(
                type=NotificationType.VOLUME_WARNING if w.kind == WarningKind.DATA else NotificationType.EXPIRY_WARNING,
                title=title_fa, body=body_fa, title_en=title_en, body_en=body_en, target_user=u,
                via_site=True, via_bot=True, via_email=True, link=renew_path(s))
            w.notification = note
            w.save(update_fields=["notification"])
        note = w.notification
        if w.site_sent_at is None:
            d = NotificationDelivery.objects.create(notification=note, user=u, channel=DeliveryChannel.SITE)
            st, err = _deliver_site(u, note, d)
            if st != d.status or err:
                d.status, d.error = st, err
                d.save(update_fields=["status", "error"])
            w.site_sent_at = now
            out["site"] += 1
        held = quiet is not None or w.due_at > now
        if not held and w.bot_sent_at is None:
            ok, err = _bot(u, s, f"<b>{html.escape(title_fa if u.language != 'en' else title_en)}</b>\n\n"
                                 f"{html.escape(body_fa if u.language != 'en' else body_en)}")
            NotificationDelivery.objects.create(notification=note, user=u, channel=DeliveryChannel.BOT,
                                                status=DeliveryStatus.SENT if ok else DeliveryStatus.FAILED, error=err[:250])
            w.bot_sent_at, w.bot_error = now, err[:200]
            out["bot"] += ok
        if not held and w.email_sent_at is None:
            body = (body_fa if u.language != "en" else body_en)
            st, err = _deliver_email(u, title_fa if u.language != "en" else title_en, body)
            NotificationDelivery.objects.create(notification=note, user=u, channel=DeliveryChannel.EMAIL, status=st, error=err[:250])
            w.email_sent_at, w.email_error = now, (err or "")[:200]
            out["email"] += st == DeliveryStatus.SENT
        if held and w.due_at <= now and quiet is not None:
            w.due_at = quiet
        w.save()
    return out


def _bot(user, service, text) -> tuple[bool, str]:
    if not user.telegram_id:
        return False, "no telegram"
    try:
        from apps.telegram.config import sales_client

        client = sales_client()
        if client is None:
            return False, "sales bot not configured"
        btn = "🔄 Renew" if user.language == "en" else "🔄 تمدید"
        client.send_message(user.telegram_id, text, reply_markup={"inline_keyboard": [[{"text": btn, "callback_data": f"s:{service.id}:rn"}]]})
        return True, ""
    except Exception as exc:  # noqa: BLE001
        log.warning("retention bot message to %s failed: %s", user.id, exc)
        return False, str(exc)


def _renewed_since(service, since) -> bool:
    from apps.orders.models import Order

    return Order.objects.filter(user=service.user, status__in=("paid", "completed"), created_at__gte=since).filter(
        type__in=("renew", "new", "addon_volume")).filter(
        models_q_service_or_new(service)).exists()


def models_q_service_or_new(service):
    from django.db.models import Q

    return Q(service=service) | Q(type="new")


def mark_conversions(now) -> int:
    n = 0
    window = timedelta(days=setting("retention_conversion_days"))
    for w in ServiceWarning.objects.filter(renewed_at__isnull=True, created_at__gte=now - window).select_related("service__user"):
        if _renewed_since(w.service, w.created_at):
            w.renewed_at = now
            w.save(update_fields=["renewed_at"])
            n += 1
    return n


# --- win-back --------------------------------------------------------------------------
def run_winback() -> dict:
    from apps.panel.models import Service

    from .services import log as crm_log
    from .services import refresh_stage

    now = timezone.now()
    marked = opened = won = messaged = 0
    for s in Service.objects.filter(status__in=ENDED, user__deleted_at__isnull=True).select_related("user", "crm_end"):
        if getattr(s, "crm_end", None) is None:
            ended = s.expire_at if s.status == "expired" and s.expire_at and s.expire_at <= now else now
            ServiceEndMark.objects.create(service=s, status=s.status, ended_at=ended)
            marked += 1
    ServiceEndMark.objects.filter(service__status__in=LIVE).delete()
    grace = timedelta(hours=setting("retention_grace_hours"))
    for m in ServiceEndMark.objects.filter(ended_at__lte=now - grace).select_related("service__user"):
        s, u = m.service, m.service.user
        if u.deleted_at or u.services.filter(status__in=LIVE).exists():
            continue
        if FollowUpCase.objects.filter(service=s, kind=CaseKind.WINBACK).filter(opened_at__gte=m.ended_at).exists():
            continue
        case = FollowUpCase.objects.create(user=u, service=s, kind=CaseKind.WINBACK, ended_at=m.ended_at,
                                           last_online_at=s.online_at, inactive_since=m.ended_at)
        crm_log(u, EventKind.CASE_OPENED, case=case, case_kind=CaseKind.WINBACK, service=s.panel_username)
        opened += 1
        if setting("retention_auto_winback"):
            tpl = _auto_template()
            if tpl is not None:
                send_winback(case, None, template=tpl, via_site=True, via_bot=True, via_email=False, auto=True)
                case.auto_message_at = now
                case.save(update_fields=["auto_message_at", "updated_at"])
                messaged += 1
        refresh_stage(u)
    window = timedelta(days=setting("retention_winback_days"))
    for case in FollowUpCase.objects.filter(kind=CaseKind.WINBACK, status=CaseStatus.OPEN).select_related("user"):
        if case.user.services.filter(status__in=LIVE).exists() and now - case.opened_at <= window + timedelta(days=1):
            from apps.payments_sms.models import Payment

            got = Payment.objects.filter(order__user=case.user, status="approved", confirmed_at__gte=case.opened_at) \
                .aggregate(s=Sum("amount"))["s"] or Decimal(0)
            case.recovered_amount = got
            case.save(update_fields=["recovered_amount", "updated_at"])
            from .services import close

            close(case, None, Outcome.WON_BACK, note="renewed / bought again (detected by the system)")
            won += 1
    return {"marked": marked, "opened": opened, "won_back": won, "messaged": messaged}


def _auto_template():
    tid = setting("retention_auto_winback_template")
    qs = MessageTemplate.objects.filter(is_active=True, category=Category.WINBACK)
    return (qs.filter(pk=tid).first() if tid else None) or qs.first()


def send_winback(case, staff, *, template=None, body_fa="", body_en="", via_site=True, via_bot=True, via_email=False, auto=False):
    """A win-back message: the template may use {renew}, and {code} {percent} {code_expires} of the
    customer's active discount code (if any)."""
    from .services import send_message

    code = active_code(case.user)
    if template is not None:
        from .services import render

        body_fa, body_en = render(template, case.user, case.service)
    extra = {"renew": site_url() + (renew_path(case.service) if case.service else "/store"),
             "code": code.code if code else "", "percent": str(code.percent) if code else "",
             "code_expires": code.expires_at.astimezone(TZ).strftime("%Y-%m-%d") if code else ""}
    for k, v in extra.items():
        body_fa, body_en = body_fa.replace("{" + k + "}", v), (body_en or "").replace("{" + k + "}", v)
    return send_message(case.user, staff, body_fa=body_fa, body_en=body_en, case=case, via_site=via_site, via_bot=via_bot,
                        via_email=via_email, auto=auto)


# --- discount codes ----------------------------------------------------------------------
_ALPHA = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def active_code(user):
    return DiscountCode.objects.filter(user=user, used_at__isnull=True, expires_at__gt=timezone.now()).order_by("-created_at").first()


def issue_code(case, staff, *, percent=None, days=None) -> DiscountCode:
    from .services import log as crm_log

    if active_code(case.user) is not None:
        raise RetentionError("this customer already has an active discount code", "has_code", 409)
    percent = int(percent or setting("retention_discount_percent"))
    days = int(days or setting("retention_discount_days"))
    if not 1 <= percent <= 90 or not 1 <= days <= 90:
        raise RetentionError("percent 1–90, days 1–90", "invalid")
    for _ in range(5):
        code = "WB" + "".join(secrets.choice(_ALPHA) for _ in range(8))
        if not DiscountCode.objects.filter(code=code).exists():
            break
    dc = DiscountCode.objects.create(code=code, user=case.user, percent=percent, expires_at=timezone.now() + timedelta(days=days),
                                     case=case, created_by=staff.username if staff else "system")
    crm_log(case.user, EventKind.DISCOUNT, staff=staff, case=case, code=code, percent=percent, days=days)
    from apps.common.models import write_audit

    write_audit(action="crm.discount_issued", staff=staff, target=case, detail={"percent": percent, "days": days})
    return dc


def check_code(user, raw: str) -> DiscountCode:
    """A code the user may apply now (raises RetentionError otherwise)."""
    from apps.orders.models import OrderStatus

    code = (raw or "").strip().upper()
    dc = DiscountCode.objects.filter(code=code).first()
    if dc is None or dc.user_id != user.id:
        raise RetentionError("invalid discount code", "code_invalid")
    if dc.used_at is not None:
        raise RetentionError("this discount code was already used", "code_used")
    if dc.expires_at <= timezone.now():
        raise RetentionError("this discount code has expired", "code_expired")
    if dc.order_id and dc.order.status in (OrderStatus.PENDING_PAYMENT, OrderStatus.PAID) and dc.order.status != "expired":
        pass   # reserved by an open order of the same user — create_order reuses / replaces it
    return dc


def discounted(amount: Decimal, percent: int) -> tuple[Decimal, Decimal]:
    off = (Decimal(amount) * Decimal(percent) / 100).quantize(Decimal("1"))
    return Decimal(amount) - off, off


# --- reports ---------------------------------------------------------------------------
def report(days: int) -> dict:
    from django.db.models import Count

    now = timezone.now()
    since = now - timedelta(days=days) if days > 0 else None
    w = ServiceWarning.objects.exclude(bot_error__startswith="skipped")
    if since:
        w = w.filter(created_at__gte=since)
    per = {}
    for kind, thr, n, conv in w.values_list("kind", "threshold").annotate(n=Count("id"), conv=Count("renewed_at")).values_list(
            "kind", "threshold", "n", "conv"):
        per[f"{kind}:{thr}"] = {"kind": kind, "threshold": thr, "sent": n, "renewed": conv,
                                "rate": round(conv * 100 / n, 1) if n else None}
    ends = ServiceEndMark.objects.all()
    cases = FollowUpCase.objects.filter(kind=CaseKind.WINBACK)
    closed = cases.filter(status=CaseStatus.CLOSED)
    if since:
        ends, cases, closed = ends.filter(ended_at__gte=since), cases.filter(opened_at__gte=since), closed.filter(closed_at__gte=since)
    won = closed.filter(outcome=Outcome.WON_BACK)
    reasons = {}
    for rid, fa, en, n in closed.exclude(reason__isnull=True).values_list("reason", "reason__name_fa", "reason__name_en").annotate(
            n=Count("id")).values_list("reason", "reason__name_fa", "reason__name_en", "n"):
        reasons[rid] = {"id": rid, "name_fa": fa, "name_en": en, "count": n}
    return {
        "days": days,
        "warnings": sorted(per.values(), key=lambda x: (x["kind"], -x["threshold"])),
        "warnings_total": sum(x["sent"] for x in per.values()),
        "renewed_after_warning": sum(x["renewed"] for x in per.values()),
        "expired_now": ServiceEndMark.objects.count(), "ended_in_period": ends.count(),
        "winback_opened": cases.count(), "winback_open": FollowUpCase.objects.filter(kind=CaseKind.WINBACK, status=CaseStatus.OPEN).count(),
        "won_back": won.count(), "lost": closed.filter(outcome=Outcome.LOST).count(),
        "winback_rate": round(won.count() * 100 / closed.count(), 1) if closed.count() else None,
        "recovered": str(won.aggregate(s=Sum("recovered_amount"))["s"] or 0),
        "top_reasons": sorted(reasons.values(), key=lambda x: -x["count"])[:8],
        "codes_issued": DiscountCode.objects.filter(created_at__gte=since).count() if since else DiscountCode.objects.count(),
        "codes_used": DiscountCode.objects.filter(used_at__isnull=False, **({"used_at__gte": since} if since else {})).count(),
    }
