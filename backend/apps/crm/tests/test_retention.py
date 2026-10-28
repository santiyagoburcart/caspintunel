"""Retention: pre-expiry warnings (thresholds, once per period, quiet hours, channels,
renew button, conversion), win-back queue (grace, auto won-back + recovered money,
discount codes at checkout), reports, timeline."""
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.crm import retention as R
from apps.crm.models import DiscountCode, FollowUpCase, ServiceEndMark, ServiceWarning
from apps.notifications.models import NotificationDelivery
from apps.orders.models import Order
from apps.orders.services import OrderError, create_order
from apps.panel.models import Panel, Service
from apps.payments_sms.models import Payment
from apps.plans.models import Plan
from apps.settings_app.models import ValueType
from apps.settings_app.utils import set_setting

from .test_crm import client_for, customer, staff

pytestmark = pytest.mark.django_db
GB = 1024 ** 3
TEHRAN = ZoneInfo("Asia/Tehran")


@pytest.fixture(autouse=True)
def _panel_fresh(monkeypatch):
    """These tests are about the reminder rules; the live re-check is in panel/tests/test_sync.py."""
    monkeypatch.setattr("apps.crm.retention.fresh_service", lambda s: s)


@pytest.fixture
def panel():
    return Panel.objects.create(name="p", base_url="https://p.test", admin_username="a", admin_password_enc="x")


@pytest.fixture
def plan(panel):
    return Plan.objects.create(name_fa="ماهانه", name_en="Monthly", price=200000, data_limit=50 * GB, duration_days=30, panel=panel)


@pytest.fixture
def bot(monkeypatch):
    sent = []

    class Fake:
        def send_message(self, chat_id, text, reply_markup=None, **kw):
            sent.append((chat_id, text, reply_markup))

    monkeypatch.setattr("apps.telegram.config.sales_client", lambda: Fake())
    return sent


@pytest.fixture
def daytime(monkeypatch):
    """Outside the default quiet hours (00:00–08:00 Tehran)."""
    noon = datetime(2026, 10, 22, 12, 0, tzinfo=TEHRAN)
    monkeypatch.setattr(R.timezone, "now", lambda: noon.astimezone(ZoneInfo("UTC")))
    return noon


def svc(u, panel, plan=None, *, used=0, days_left=20, status="active"):
    return Service.objects.create(user=u, panel=panel, panel_username=f"{u.username}_{Service.objects.count()}", status=status,
                                  data_limit=50 * GB, data_used=int(used * GB), current_plan=plan,
                                  expire_at=R.timezone.now() + timedelta(days=days_left, hours=2), last_synced_at=R.timezone.now())


# --- warnings ----------------------------------------------------------------------------
def test_thresholds_once_per_period_and_strongest_only(panel, bot, daytime):
    u = customer(telegram_id=11, email="ali@example.test")
    s = svc(u, panel, used=41)                     # 82 %
    assert R.run_warnings()["created"] == 1
    assert R.run_warnings()["created"] == 0        # never twice
    s.data_used = int(49 * GB)                     # 98 %
    s.save()
    assert R.run_warnings()["created"] == 1
    assert list(ServiceWarning.objects.order_by("threshold").values_list("kind", "threshold")) == [("data", 80), ("data", 95)]
    # straight to 96 % on a fresh service: only the 95 % warning goes out, 80 % is recorded as skipped
    v = customer("bea", telegram_id=12)
    svc(v, panel, used=48.5)
    R.run_warnings()
    ws = {w.threshold: w for w in ServiceWarning.objects.filter(service__user=v)}
    assert ws[80].bot_error.startswith("skipped") and not ws[95].bot_error
    assert [c for c, *_ in bot].count(12) == 1
    # renewal = new period → the thresholds can fire again
    s.expire_at = s.expire_at + timedelta(days=30)
    s.data_used = int(41 * GB)
    s.save()
    assert R.run_warnings()["created"] == 1


def test_time_warnings_channels_and_renew_button(panel, bot, daytime):
    u = customer(telegram_id=21, email="a@example.test")
    s = svc(u, panel, days_left=2)
    R.run_warnings()
    w = ServiceWarning.objects.get()
    assert (w.kind, w.threshold) == ("time", 3) and w.site_sent_at and w.bot_sent_at and w.email_sent_at
    chat, text, markup = bot[-1]
    assert chat == 21 and s.panel_username in text and markup["inline_keyboard"][0][0]["callback_data"] == f"s:{s.id}:rn"
    assert w.notification.link == f"/renew/{s.id}" and "{" not in w.notification.body
    assert set(NotificationDelivery.objects.filter(user=u).values_list("channel", flat=True)) == {"site", "bot", "email"}
    # a service with less than a day left gets only the 1-day warning (3 days recorded as skipped)
    v = customer("bea", telegram_id=22)
    t = svc(v, panel, days_left=0)
    R.run_warnings()
    ws = {w.threshold: w for w in ServiceWarning.objects.filter(service=t)}
    assert set(ws) == {1, 3} and ws[3].bot_error.startswith("skipped") and not ws[1].bot_error


def test_quiet_hours_hold_bot_and_email_until_morning(panel, bot, monkeypatch):
    night = datetime(2026, 10, 22, 2, 0, tzinfo=TEHRAN)
    monkeypatch.setattr(R.timezone, "now", lambda: night.astimezone(ZoneInfo("UTC")))
    u = customer(telegram_id=31)
    svc(u, panel, days_left=2)
    R.run_warnings()
    w = ServiceWarning.objects.get()
    assert w.site_sent_at and w.bot_sent_at is None and w.email_sent_at is None and bot == []
    assert w.due_at.astimezone(TEHRAN).hour == 8
    morning = datetime(2026, 10, 22, 8, 30, tzinfo=TEHRAN)
    monkeypatch.setattr(R.timezone, "now", lambda: morning.astimezone(ZoneInfo("UTC")))
    R.run_warnings()
    R.run_warnings()
    w.refresh_from_db()
    assert w.bot_sent_at and len(bot) == 1                                     # sent once, never duplicated
    assert NotificationDelivery.objects.filter(user=u, channel="site").count() == 1


def test_warnings_replace_the_old_alert(panel, bot, daytime):
    from apps.ops.tasks import service_alerts_task

    u = customer(telegram_id=41)
    s = svc(u, panel, used=45)
    service_alerts_task()
    s.refresh_from_db()
    assert ServiceWarning.objects.count() == 1 and not s.alert_vol_sent           # old flags untouched
    set_setting("retention_warnings_enabled", False, ValueType.BOOL)
    service_alerts_task()
    s.refresh_from_db()
    assert s.alert_vol_sent


def test_conversion_after_warning(panel, plan, bot, daytime):
    u = customer(telegram_id=51)
    s = svc(u, panel, plan, days_left=2)
    R.run_warnings()
    Order.objects.create(user=u, plan=plan, service=s, type="renew", amount=1, amount_unique=1001, unique_expire_at=R.timezone.now(),
                         status="completed")
    R.run_warnings()
    assert ServiceWarning.objects.get().renewed_at is not None


# --- win-back ------------------------------------------------------------------------------
def test_winback_grace_case_and_auto_won_back(panel, plan, monkeypatch):
    u = customer()
    s = svc(u, panel, plan, used=50, status="limited")
    R.run_winback()
    assert ServiceEndMark.objects.filter(service=s).exists() and not FollowUpCase.objects.exists()   # within grace
    ServiceEndMark.objects.filter(service=s).update(ended_at=timezone.now() - timedelta(hours=30))
    assert R.run_winback()["opened"] == 1
    case = FollowUpCase.objects.get()
    assert case.kind == "winback" and case.status == "open"
    assert R.run_winback()["opened"] == 0
    # renewed + paid → won back, recovered money recorded
    o = Order.objects.create(user=u, plan=plan, service=s, type="renew", amount=180000, amount_unique=181000,
                             unique_expire_at=timezone.now(), status="completed")
    Payment.objects.create(order=o, amount=181000, status="approved", method="sms_auto", confirmed_at=timezone.now())
    s.status = "active"
    s.save()
    assert R.run_winback()["won_back"] == 1
    case.refresh_from_db()
    assert case.outcome == "won_back" and case.recovered_amount == 181000 and case.closed_by_system
    assert not ServiceEndMark.objects.filter(service=s).exists()


def test_no_winback_when_customer_still_has_a_live_service(panel, plan):
    u = customer()
    s = svc(u, panel, plan, status="expired", days_left=-3)
    svc(u, panel, plan)
    R.run_winback()
    ServiceEndMark.objects.filter(service=s).update(ended_at=timezone.now() - timedelta(days=3))
    assert R.run_winback()["opened"] == 0


def test_auto_winback_message_off_then_on(panel, plan):
    u = customer(telegram_id=61)
    s = svc(u, panel, plan, status="expired", days_left=-3)
    other = customer("quiet")
    svc(other, panel, plan, status="expired", days_left=-3)
    R.run_winback()                                    # off by default: case, no message
    assert FollowUpCase.objects.filter(user=other).exists() and not NotificationDelivery.objects.filter(user=other).exists()
    FollowUpCase.objects.filter(user=u).delete()
    set_setting("retention_auto_winback", True, ValueType.BOOL)
    assert R.run_winback()["messaged"] == 1
    body = NotificationDelivery.objects.filter(user=u, channel="site").last().notification.body
    assert f"/renew/{s.id}" in body and "{renew}" not in body


# --- discount codes ------------------------------------------------------------------------
def test_discount_code_issue_and_checkout(panel, plan):
    u = customer()
    s = svc(u, panel, plan, status="expired", days_left=-3)
    case = FollowUpCase.objects.create(user=u, service=s, kind="winback")
    agent = staff("agent", ["crm.view", "crm.manage"])
    c = client_for(agent)
    r = c.post(f"/api/v1/admin/crm/cases/{case.id}/discount/", {"percent": 20, "days": 5}, format="json")
    assert r.status_code == 201
    code = r.json()["code"]
    assert c.post(f"/api/v1/admin/crm/cases/{case.id}/discount/", {}, format="json").status_code == 409     # one per customer
    with pytest.raises(OrderError):
        create_order(user=customer("intruder"), plan_id=plan.id, order_type="new", requested_account_name="x1", discount_code=code)
    o = create_order(user=u, plan_id=plan.id, order_type="renew", service_id=s.id, discount_code=code.lower())
    assert o.amount == Decimal(plan.final_price) * Decimal("0.8") and o.discount_amount == Decimal(plan.final_price) * Decimal("0.2")
    assert DiscountCode.objects.get(code=code).order == o
    # the same purchase again with the code returns the same discounted invoice
    assert create_order(user=u, plan_id=plan.id, order_type="renew", service_id=s.id, discount_code=code).id == o.id
    o.status = "paid"
    o.save()
    assert DiscountCode.objects.get(code=code).used_at is not None
    with pytest.raises(OrderError, match="already used"):
        create_order(user=u, plan_id=plan.id, order_type="renew", service_id=s.id, discount_code=code)


def test_discount_code_replaces_undiscounted_pending_invoice_and_expires(panel, plan):
    u = customer()
    s = svc(u, panel, plan, status="expired", days_left=-3)
    plain = create_order(user=u, plan_id=plan.id, order_type="renew", service_id=s.id)
    case = FollowUpCase.objects.create(user=u, service=s, kind="winback")
    dc = R.issue_code(case, None, percent=10, days=3)
    o = create_order(user=u, plan_id=plan.id, order_type="renew", service_id=s.id, discount_code=dc.code)
    plain.refresh_from_db()
    assert o.id != plain.id and plain.status == "expired" and o.discount_amount > 0
    DiscountCode.objects.filter(pk=dc.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
    with pytest.raises(OrderError, match="expired"):
        R_order = create_order(user=u, plan_id=plan.id, order_type="renew", service_id=s.id, discount_code=dc.code)  # noqa: F841


def test_winback_message_renders_code_and_renew(panel, plan):
    from apps.crm.models import MessageTemplate

    u = customer(telegram_id=71)
    s = svc(u, panel, plan, status="expired", days_left=-3)
    case = FollowUpCase.objects.create(user=u, service=s, kind="winback")
    R.issue_code(case, None, percent=15, days=7)
    c = client_for(staff("m", ["crm.view", "crm.manage"]))
    tpl = MessageTemplate.objects.get(category="winback")
    assert c.post(f"/api/v1/admin/crm/cases/{case.id}/message/", {"template": tpl.id, "via_bot": False}, format="json").status_code == 200
    body = NotificationDelivery.objects.filter(user=u).last().notification.body
    code = DiscountCode.objects.get().code
    assert code in body and "15" in body and f"/renew/{s.id}" in body and "{" not in body
    row = c.get(f"/api/v1/admin/crm/cases/{case.id}/").json()
    assert row["discount"]["code"] == code and row["ltv"] == "0" and row["plan"]["name_en"] == "Monthly"


# --- reports, settings, timeline, permissions --------------------------------------------------------
def test_reports_settings_timeline(panel, plan, bot, daytime, monkeypatch):
    u = customer(telegram_id=81)
    s = svc(u, panel, plan, days_left=2)
    R.run_warnings()
    monkeypatch.undo()                       # real clock again (staff tokens)
    case = FollowUpCase.objects.create(user=u, service=s, kind="winback")
    from apps.crm import services as S

    S.close(case, None, "won_back")
    FollowUpCase.objects.filter(pk=case.pk).update(recovered_amount=150000)
    c = client_for(staff("v", ["crm.view", "crm.manage"]))
    r = c.get("/api/v1/admin/crm/retention/report/?days=30")
    assert r.status_code == 200, r.content[:400]
    d = r.json()
    assert d["warnings_total"] == 1 and d["warnings"][0]["threshold"] == 3 and d["won_back"] == 1
    assert d["winback_rate"] == 100.0 and d["recovered"] == "150000"
    r = c.patch("/api/v1/admin/crm/retention/settings/", {"retention_quiet_start": "25:99"}, format="json")
    assert r.status_code == 400
    st = c.patch("/api/v1/admin/crm/retention/settings/", {"retention_grace_hours": 48, "retention_quiet_end": "07:30"}, format="json").json()
    assert st["settings"]["retention_grace_hours"] == 48 and st["settings"]["retention_quiet_end"] == "07:30"
    kinds = [x["kind"] for x in c.get(f"/api/v1/admin/crm/customers/{u.id}/timeline/").json()]
    assert "warning" in kinds
    rules = c.get("/api/v1/admin/crm/warning-rules/").json()
    assert sorted((r["kind"], r["threshold"]) for r in rules) == [("data", 80), ("data", 95), ("time", 1), ("time", 3)]
    assert c.post("/api/v1/admin/crm/warning-rules/", {"kind": "data", "threshold": 80, "title_fa": "x", "body_fa": "y"},
                  format="json").status_code == 409
    assert len(c.get("/api/v1/admin/crm/reasons/?category=winback").json()) == 6
    assert client_for(staff("x", ["tickets.view"])).get("/api/v1/admin/crm/retention/report/").status_code == 403
