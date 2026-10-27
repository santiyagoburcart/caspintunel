"""CRM rules: settings, lifecycle stage, inactivity detection, case actions.

Stage (computed, `refresh_stage`; a manual override wins until cleared):
  lead      registered, never bought (no paid / completed order)
  new       has a live service (active / on_hold) and the first purchase was within crm_new_days
  active    has a live service
  at_risk   live service AND (an open inactivity case, or expiring within crm_at_risk_days,
            or crm_at_risk_usage_pct of the volume used)
  expired   no live service, the last one ended less than crm_churn_days ago
  churned   no live service for crm_churn_days or more
  won_back  live again after being expired / churned — kept for crm_won_back_days

Detection (`detect_inactivity`, hourly beat), only on services synced in the last 24 h:
  no_connection    status active, last connection (online_at) older than crm_inactive_days
  never_connected  on_hold, or active without any connection, created more than
                   crm_never_connected_hours ago
  One open case per service. A case closes itself (outcome resolved, by the system)
  once the service connects again. Optional friendly message after
  crm_auto_message_days (setting crm_auto_message, off by default).
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.common.models import write_audit
from apps.settings_app.utils import get_setting

from .models import (
    CaseKind,
    CaseReason,
    CaseStatus,
    CrmEvent,
    CustomerProfile,
    EventKind,
    FollowUpCase,
    MessageTemplate,
    Outcome,
    Stage,
)

LIVE = ("active", "on_hold")
BOUGHT = ("paid", "completed")

# key, default, min, max
INT_SETTINGS = [
    ("crm_inactive_days", 3, 1, 60),
    ("crm_never_connected_hours", 48, 1, 720),
    ("crm_new_days", 14, 1, 90),
    ("crm_at_risk_days", 3, 0, 30),
    ("crm_at_risk_usage_pct", 90, 50, 100),
    ("crm_churn_days", 30, 1, 365),
    ("crm_won_back_days", 30, 1, 365),
    ("crm_auto_message_days", 5, 1, 60),
    ("crm_auto_message_template", 0, 0, 1_000_000),      # 0 = the first active template
]
BOOL_SETTINGS = [("crm_auto_message", False)]
STR_SETTINGS = [("crm_guide_url", "")]                   # {guide} in templates; empty = <site>/help


class CrmError(ValueError):
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


def _label(staff) -> str:
    return f"staff:{staff.username}" if staff is not None else "system"


def log(user, kind, *, staff=None, case=None, **detail) -> CrmEvent:
    return CrmEvent.objects.create(user=user, kind=kind, actor_label=_label(staff), case=case, detail=detail)


def profile(user) -> CustomerProfile:
    p, _ = CustomerProfile.objects.get_or_create(user=user, defaults={"stage": compute_stage(user)})
    return p


# --- lifecycle stage ---------------------------------------------------------------
def _base_stage(user, now) -> str:
    orders = user.orders.filter(status__in=BOUGHT)
    first = orders.order_by("created_at").values_list("created_at", flat=True).first()
    if first is None:
        return Stage.LEAD
    live = list(user.services.filter(status__in=LIVE))
    if not live:
        ended = user.services.exclude(expire_at__isnull=True).order_by("-expire_at").values_list("expire_at", flat=True).first()
        ended = ended or user.services.order_by("-updated_at").values_list("updated_at", flat=True).first() or first
        return Stage.CHURNED if now - ended >= timedelta(days=setting("crm_churn_days")) else Stage.EXPIRED
    risky_until = now + timedelta(days=setting("crm_at_risk_days"))
    pct = setting("crm_at_risk_usage_pct") / 100
    if FollowUpCase.objects.filter(user=user, status=CaseStatus.OPEN, kind__in=(CaseKind.NO_CONNECTION, CaseKind.NEVER_CONNECTED)).exists() \
            or any((s.expire_at and s.expire_at <= risky_until) or (s.data_limit and s.data_used >= s.data_limit * pct) for s in live):
        return Stage.AT_RISK
    if now - first <= timedelta(days=setting("crm_new_days")):
        return Stage.NEW
    return Stage.ACTIVE


def compute_stage(user, previous: str | None = None, changed_at=None) -> str:
    now = timezone.now()
    base = _base_stage(user, now)
    if base in (Stage.NEW, Stage.ACTIVE):
        if previous in (Stage.EXPIRED, Stage.CHURNED):
            return Stage.WON_BACK
        if previous == Stage.WON_BACK and changed_at and now - changed_at < timedelta(days=setting("crm_won_back_days")):
            return Stage.WON_BACK
    return base


def refresh_stage(user) -> CustomerProfile:
    p = profile(user)
    new = compute_stage(user, p.stage, p.stage_changed_at)
    if new != p.stage:
        old = p.stage
        p.stage, p.stage_changed_at = new, timezone.now()
        p.save(update_fields=["stage", "stage_changed_at", "updated_at"])
        log(user, EventKind.STAGE, old=old, new=new)
    return p


def ltv(user) -> Decimal:
    from apps.payments_sms.models import Payment

    return Payment.objects.live().filter(order__user=user, status="approved").aggregate(s=Sum("amount"))["s"] or Decimal(0)


# --- detection ----------------------------------------------------------------------
def _open_case(service, kind, *, last_online=None, since=None):
    if FollowUpCase.objects.filter(service=service, status=CaseStatus.OPEN).exists():
        return None
    case = FollowUpCase.objects.create(user=service.user, service=service, kind=kind, last_online_at=last_online,
                                       inactive_since=since)
    log(service.user, EventKind.CASE_OPENED, case=case, case_kind=kind, service=service.panel_username)
    return case


def detect_inactivity() -> dict:
    from apps.panel.models import Service

    now = timezone.now()
    fresh = now - timedelta(hours=24)
    inactive_cut = now - timedelta(days=setting("crm_inactive_days"))
    never_cut = now - timedelta(hours=setting("crm_never_connected_hours"))
    opened = closed = messaged = 0
    base = Service.objects.filter(last_synced_at__gte=fresh, user__deleted_at__isnull=True).select_related("user")
    with transaction.atomic():
        for s in base.filter(status="active", online_at__lt=inactive_cut):
            if _open_case(s, CaseKind.NO_CONNECTION, last_online=s.online_at, since=s.online_at):
                opened += 1
        for s in base.filter(Q(status="on_hold") | Q(status="active"), online_at__isnull=True, created_at__lt=never_cut):
            if _open_case(s, CaseKind.NEVER_CONNECTED, since=s.created_at):
                opened += 1
    # a service that connected again closes its case
    for case in FollowUpCase.objects.filter(status=CaseStatus.OPEN, kind__in=(CaseKind.NO_CONNECTION, CaseKind.NEVER_CONNECTED),
                                            service__isnull=False).select_related("service", "user"):
        s = case.service
        if s.online_at and s.online_at > (case.last_online_at or case.opened_at - timedelta(days=3650)) \
                and s.online_at >= now - timedelta(days=setting("crm_inactive_days")):
            close(case, None, Outcome.RESOLVED, note="connected again (detected by the system)")
            closed += 1
    if setting("crm_auto_message"):
        messaged = _auto_messages(now)
    for uid in set(FollowUpCase.objects.filter(updated_at__gte=now - timedelta(minutes=5)).values_list("user_id", flat=True)):
        from apps.accounts.models import User

        refresh_stage(User.objects.get(pk=uid))
    return {"opened": opened, "closed": closed, "messaged": messaged}


def _auto_messages(now) -> int:
    tpl = default_template()
    if tpl is None:
        return 0
    cut = now - timedelta(days=setting("crm_auto_message_days"))
    n = 0
    for case in FollowUpCase.objects.filter(status=CaseStatus.OPEN, auto_message_at__isnull=True, inactive_since__lt=cut,
                                            kind__in=(CaseKind.NO_CONNECTION, CaseKind.NEVER_CONNECTED)).select_related("user", "service"):
        send_message(case.user, None, template=tpl, case=case, via_bot=True, via_site=True, auto=True)
        case.auto_message_at = now
        case.save(update_fields=["auto_message_at", "updated_at"])
        n += 1
    return n


def default_template():
    tid = setting("crm_auto_message_template")
    qs = MessageTemplate.objects.filter(is_active=True, category="inactivity")
    return (qs.filter(pk=tid).first() if tid else None) or qs.first()


# --- case actions ----------------------------------------------------------------------
def open_manual(user, staff, *, kind=CaseKind.MANUAL, notes="", service=None) -> FollowUpCase:
    case = FollowUpCase.objects.create(user=user, kind=kind, notes=notes, assigned_to=staff, service=service)
    log(user, EventKind.CASE_OPENED, staff=staff, case=case, case_kind=kind)
    write_audit(action="crm.case_opened", staff=staff, target=case, detail={"user": user.id, "kind": kind})
    return case


def update_case(case, staff, *, reason_id=..., notes=None, assigned_to=...) -> FollowUpCase:
    changed = {}
    if reason_id is not ...:
        reason = CaseReason.objects.filter(pk=reason_id).first() if reason_id else None
        if reason_id and reason is None:
            raise CrmError("unknown reason", "reason")
        case.reason, changed["reason"] = reason, reason.name_en if reason else None
    if notes is not None:
        case.notes, changed["notes"] = notes[:4000], True
    if assigned_to is not ...:
        case.assigned_to, changed["assigned_to"] = assigned_to, assigned_to.username if assigned_to else None
    if changed:
        case.save()
        log(case.user, EventKind.CASE_UPDATED, staff=staff, case=case, **changed)
        write_audit(action="crm.case_updated", staff=staff, target=case, detail=changed)
    return case


def close(case, staff, outcome, *, note="") -> FollowUpCase:
    if outcome not in Outcome.values:
        raise CrmError("unknown outcome", "outcome")
    if case.status == CaseStatus.CLOSED:
        raise CrmError("this case is already closed", "closed", 409)
    case.status, case.outcome = CaseStatus.CLOSED, outcome
    case.closed_at, case.closed_by, case.closed_by_system = timezone.now(), staff, staff is None
    if note:
        case.notes = (case.notes + "\n" + note).strip() if case.notes else note
    case.save()
    log(case.user, EventKind.CASE_CLOSED, staff=staff, case=case, outcome=outcome)
    if staff is not None:
        write_audit(action="crm.case_closed", staff=staff, target=case, detail={"outcome": outcome})
    refresh_stage(case.user)
    return case


def render(template, user, service=None) -> tuple[str, str]:
    from apps.settings_app.models import SiteConfig

    cfg = SiteConfig.load()
    domain = (cfg.site_domain or "").strip().strip("/")
    site = f"https://{domain}" if domain else ""
    guide = setting("crm_guide_url") or (f"{site}/help" if site else "")
    vals = {"name": user.name or user.username, "username": user.username, "service": service.panel_username if service else "",
            "site": site, "guide": guide}

    class _Safe(dict):
        def __missing__(self, k):
            return "{" + k + "}"

    fa = template.body_fa.format_map(_Safe(vals))
    en = (template.body_en or template.body_fa).format_map(_Safe(vals))
    return fa, en


def send_message(user, staff, *, template=None, body_fa="", body_en="", case=None, via_site=True, via_bot=True,
                 via_email=False, auto=False):
    from apps.notifications.dispatch import notify_user

    if template is not None:
        body_fa, body_en = render(template, user, case.service if case else None)
    body_fa = (body_fa or "").strip()
    if not body_fa:
        raise CrmError("the message is empty", "empty")
    if not (via_site or via_bot or via_email):
        raise CrmError("pick at least one channel", "channels")
    note = notify_user(user, title="پیام پشتیبانی", title_en="A message from support", body=body_fa, body_en=body_en or body_fa,
                       via_site=via_site, via_bot=via_bot, via_email=via_email, staff=staff, link="/tickets")
    channels = [c for c, on in (("site", via_site), ("bot", via_bot), ("email", via_email)) if on]
    log(user, EventKind.MESSAGE, staff=staff, case=case, channels=channels, auto=auto,
        template=template.title if template else None, preview=body_fa[:140])
    if staff is not None:
        write_audit(action="crm.message_sent", staff=staff, target=case or user, detail={"user": user.id, "channels": channels})
    return note


def open_ticket_for(case, staff, *, topic_id, subject, body):
    from apps.tickets.services import open_for_user

    ticket = open_for_user(case.user, staff, topic_id=topic_id, subject=subject, body=body)
    case.ticket = ticket
    case.save(update_fields=["ticket", "updated_at"])
    log(case.user, EventKind.TICKET, staff=staff, case=case, ticket=ticket.number, by_staff=True)
    return ticket


def link_ticket(ticket) -> FollowUpCase | None:
    """A new ticket in the connection-problem topic joins the customer's open inactivity case."""
    case = FollowUpCase.objects.filter(user=ticket.user, status=CaseStatus.OPEN, ticket__isnull=True,
                                       kind__in=(CaseKind.NO_CONNECTION, CaseKind.NEVER_CONNECTED)).order_by("-opened_at").first()
    if case is None:
        return None
    case.ticket = ticket
    case.save(update_fields=["ticket", "updated_at"])
    log(ticket.user, EventKind.TICKET, case=case, ticket=ticket.number, by_staff=False)
    return case


def connection_topic_id():
    from apps.tickets.models import TicketTopic

    tid = get_setting("crm_connection_topic_id", None)
    if tid:
        return int(tid)
    t = TicketTopic.objects.filter(name_en="Connection problem").first()
    return t.id if t else None


def refresh_all_stages() -> int:
    """Stages move with time (new → active, expired → churned …): recompute for every
    customer with a service, an order or a profile."""
    from apps.accounts.models import User

    changed = 0
    ids = User.objects.filter(deleted_at__isnull=True).filter(
        Q(services__isnull=False) | Q(orders__isnull=False) | Q(crm__isnull=False)).values_list("id", flat=True).distinct()
    for u in User.objects.filter(id__in=list(ids)).iterator():
        before = CustomerProfile.objects.filter(user=u).values_list("stage", flat=True).first()
        if refresh_stage(u).stage != before:
            changed += 1
    return changed
