"""v1.42.1 fixes:

1. Account names follow PasarGuard's username rule on every form (site / Mini App, bot, rename, manual invoice, staff
   new service, agency admin) — checked before payment, Persian reason + a fixed suggestion. A paid order PasarGuard still
   refuses becomes «ساخت ناموفق»: no retry loop, one staff alert with the panel's error, the customer sees «در حال
   آماده‌سازی»; staff edit the name and «تلاش دوباره». The sync never disables a service that was never created.
2. Staff-entered dates / times without an offset are Tehran time (manual invoice «قبلاً پرداخت شده»), 5 min skew.
3. Renewal: custom-volume plans renew (last volume pre-filled, the bought GB applied on the panel); a retired plan renews
   only when staff mark it renewable; services without a plan get the plan of their last paid order.
"""
import json
from datetime import timedelta
from decimal import Decimal

import pytest
import responses
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.common.models import AuditLog
from apps.notifications.models import Notification
from apps.orders.models import Order, OrderStatus, OrderType, ScheduledRenewal
from apps.orders.services import AccountNameRefused, OrderError, create_order, retry_provision
from apps.panel import account_names as AN
from apps.panel.exceptions import PanelValidationError
from apps.panel.models import Panel, Service, ServiceStatus
from apps.panel.services import apply_scheduled_renewal
from apps.payments_sms.models import Payment, PaymentStatus
from apps.payments_sms.services import approve_payment
from apps.payments_sms.tests.test_blu import staff_client
from apps.plans.models import Plan, PlanType

pytestmark = pytest.mark.django_db
BASE = "https://panel.test"
GB = 1024 ** 3


@pytest.fixture
def panel():
    return Panel.objects.create(name="P", base_url=BASE, admin_username="a", admin_password_enc="p", is_active=True)


@pytest.fixture
def plan(panel):
    return Plan.objects.create(panel=panel, name_fa="بسته اقتصادی", name_en="Eco", price=Decimal("175000"),
                               data_limit=35 * GB, duration_days=30)


@pytest.fixture
def custom(panel):
    return Plan.objects.create(panel=panel, name_fa="حجم دلخواه", price=Decimal("0"), type=PlanType.CUSTOM_VOLUME,
                               price_per_gb=Decimal("2000"), min_gb=10, max_gb=500, duration_days=30)


@pytest.fixture
def user():
    return User.objects.create_user("saharsoheili", "Str0ngPass!", telegram_id=6201)


@pytest.fixture
def free_names(monkeypatch):
    from apps.orders import services

    monkeypatch.setattr(services, "check_account_name", lambda panel, name: None)


def _api(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


# --- 1. the rule ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name,code,suggestion", [
    ("sahar 1364", "space", "sahar_1364"),
    ("سحر۱۳۶۴", "chars", "1364"),
    ("ali__2", "consecutive", "ali_2"),
    ("ab", "short", None),
    ("a" * 65, "long", "a" * 64),
    ("", "required", None),
    ("علی", "chars", None),
    ("_ali-2.", None, None),
    ("bahram_Tc", None, None),
    ("x@y.z", None, None),
])
def test_pasarguard_username_rule_and_suggestion(name, code, suggestion):
    assert AN.problem(name) == code
    assert AN.suggest(name) == suggestion
    if suggestion:
        assert AN.problem(suggestion) is None


def test_invalid_names_are_refused_before_payment_with_a_persian_reason_and_a_suggestion(user, plan, free_names):
    with pytest.raises(AccountNameRefused) as exc:
        create_order(user=user, plan_id=plan.id, requested_account_name="sahar 1364", source="bot")
    assert exc.value.suggestion == "sahar_1364" and "فاصله" in exc.value.message("fa")
    assert not Order.objects.exists()
    r = _api(user).post("/api/v1/orders/", {"plan": plan.id, "requested_account_name": "sahar 1364", "lang": "fa"},
                        format="json")
    assert r.status_code == 400 and "فاصله" in r.json()["requested_account_name"][0]
    assert r.json()["suggestion"] == ["sahar_1364"]
    r = _api(user).post("/api/v1/orders/", {"plan": plan.id, "requested_account_name": "sahar__1", "lang": "en"},
                        format="json")
    assert r.status_code == 400 and "next to each other" in r.json()["requested_account_name"][0]
    r = _api(user).post("/api/v1/orders/", {"plan": plan.id, "requested_account_name": "sahar_1364"}, format="json")
    assert r.status_code == 201, r.content


def test_staff_forms_use_the_same_rule(user, plan, panel):
    boss = staff_client("super", "rule-boss")
    r = boss.post("/api/v1/admin/services/", {"user": user.id, "plan": plan.id, "account_name": "sahar 1364"}, format="json")
    assert r.status_code == 400 and "sahar_1364" in json.dumps(r.json(), ensure_ascii=False)
    from apps.agency.admin_crud import AdminCrudError, build_payload

    with pytest.raises(AdminCrudError):
        build_payload({"username": "res__1", "password": "Str0ngPass!9x"}, creating=True)


def test_bot_name_step_explains_and_offers_the_fixed_name(monkeypatch, user, plan, free_names):
    from apps.telegram.bot import sales_bot
    from apps.telegram.tests.test_bot_gate import TG, FakeBot, _msg

    monkeypatch.setattr(sales_bot, "close_old_connections", lambda: None)
    bot = FakeBot()
    sales_bot._register(bot)
    user.telegram_id, user.terms_accepted_at = TG, timezone.now()
    user.save()
    bot.click(f"pb:{plan.id}")
    sent = bot.feed(_msg(text="sahar 1364"))
    text = " ".join(t or "" for t, _ in sent)
    assert "فاصله" in text and "sahar_1364" in text and not Order.objects.exists()
    datas = [b.callback_data for _, m in sent for row in (getattr(m, "keyboard", None) or []) for b in row]
    assert "an:sahar_1364" in datas
    bot.click("an:sahar_1364")
    o = Order.objects.get()
    assert o.requested_account_name == "sahar_1364" and o.source == "bot"


# --- 1b. provisioning refused after payment ------------------------------------------------------------------------
@pytest.fixture
def paid_new(user, plan, free_names, monkeypatch, django_capture_on_commit_callbacks):
    from apps.orders import tasks

    monkeypatch.setattr(tasks.fulfill_order, "delay", lambda oid: None)
    order = create_order(user=user, plan_id=plan.id, requested_account_name="sahar_1364")
    pay = Payment.objects.create(order=order, amount=order.amount_unique, status=PaymentStatus.PENDING)
    with django_capture_on_commit_callbacks(execute=True):
        approve_payment(pay.id)
    order.refresh_from_db()
    return order


def _refuse(monkeypatch):
    from apps.panel import services as ps

    def boom(service_id, plan=None):
        raise PanelValidationError("panel 422 on /api/user", status_code=422,
                                   body=json.dumps({"detail": [{"msg": "Username can only contain alphanumeric characters"}]}))
    monkeypatch.setattr(ps, "provision_service", boom)


def test_refused_provisioning_becomes_build_failed_with_one_alert_and_a_calm_customer_notice(monkeypatch, paid_new):
    from apps.common import staff_alert
    from apps.orders import tasks

    alerts = []
    monkeypatch.setattr(staff_alert, "alert_staff", lambda text, **kw: alerts.append((text, kw)) or 1)
    _refuse(monkeypatch)
    assert tasks.fulfill_order(paid_new.id) == {"order": paid_new.id, "status": "provision_failed"}
    paid_new.refresh_from_db()
    assert paid_new.status == OrderStatus.PAID and paid_new.provision_failed_at is not None
    assert "alphanumeric" in paid_new.provision_error
    assert len(alerts) == 1 and "alphanumeric" in alerts[0][0] and alerts[0][1]["perm"] == "payment.approve"
    n = Notification.objects.filter(target_user=paid_new.user).latest("id")
    assert "پشتیبانی پیگیری می‌کند" in n.body
    # no retry loop, no second alert
    assert tasks.retry_unfulfilled_orders() == {"redispatched": 0}
    tasks.fulfill_order(paid_new.id)
    assert len(alerts) == 1
    # the customer sees «در حال آماده‌سازی», never a broken service
    c = _api(paid_new.user)
    assert c.get(f"/api/v1/orders/{paid_new.id}/").json()["preparing"] is True
    svc = c.get(f"/api/v1/services/{paid_new.service_id}/").json()
    assert svc["preparing"] is True and svc["status"] == "pending"
    # staff see «ساخت ناموفق» with the panel's error
    boss = staff_client("super", "prov-boss")
    p = paid_new.payment
    rows = boss.get("/api/v1/admin/transactions/?provision_failed=1").json()["results"]
    assert [r["id"] for r in rows] == [p.id] and "alphanumeric" in rows[0]["provision_error"]
    assert boss.get("/api/v1/admin/transactions/provision-failed/").json()["count"] == 1


def test_staff_edit_the_name_and_retry(monkeypatch, paid_new, django_capture_on_commit_callbacks):
    from apps.orders import tasks

    _refuse(monkeypatch)
    tasks.fulfill_order(paid_new.id)
    boss = staff_client("super", "retry-boss")
    url = f"/api/v1/admin/transactions/{paid_new.payment.id}/retry-provision/"
    r = boss.post(url, {"account_name": "sahar 2"}, format="json")
    assert r.status_code == 400 and r.json()["suggestion"] == "sahar_2" and "فاصله" in r.json()["detail_fa"]
    dispatched = []
    monkeypatch.setattr(tasks.fulfill_order, "delay", lambda oid: dispatched.append(oid))
    with django_capture_on_commit_callbacks(execute=True):
        r = boss.post(url, {"account_name": "sahar_2"}, format="json")
    assert r.status_code == 200, r.content
    paid_new.refresh_from_db()
    assert dispatched == [paid_new.id] and paid_new.provision_failed_at is None and paid_new.provision_error == ""
    assert paid_new.requested_account_name == "sahar_2" and paid_new.service.panel_username == "sahar_2"
    assert AuditLog.objects.filter(action="order.provision_retry", target_id=paid_new.id,
                                   detail__to="sahar_2").exists()
    assert staff_client(["payment.view"], "viewer").post(url, {}, format="json").status_code == 403


@responses.activate
def test_sync_keeps_a_never_created_service_pending(paid_new):
    from apps.orders.tasks import _ensure_service
    from apps.panel.services import sync_service_detail

    svc = _ensure_service(paid_new, paid_new.plan.panel)
    responses.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"})
    responses.add(responses.GET, f"{BASE}/api/user/sahar_1364", status=404, json={"detail": "not found"})
    out = sync_service_detail(svc.id)
    svc.refresh_from_db()
    assert out.missing and svc.status == ServiceStatus.PENDING          # was flipped to «disabled» before v1.42.1


# --- 2. Tehran time ------------------------------------------------------------------------------------------------
def _tehran(dt):
    from apps.common.jalali import TZ

    return dt.astimezone(TZ)


@pytest.mark.parametrize("delta_min,ok", [(-200, True), (-1, True), (4, True), (10, False)])
def test_manual_paid_date_and_time_are_tehran_time(delta_min, ok, user, plan):
    import jdatetime

    from apps.orders import manual as MIs

    when = _tehran(timezone.now() + timedelta(minutes=delta_min))
    j = jdatetime.datetime.fromgregorian(datetime=when.replace(tzinfo=None))
    jalali = f"{j.year}/{j.month:02d}/{j.day:02d} {j.hour:02d}:{j.minute:02d}"
    iso_naive = f"{when.date().isoformat()}T{when.hour:02d}:{when.minute:02d}:00"   # what the admin SPA sent before
    for raw in (jalali, iso_naive):
        dt = MIs._parse_dt(raw, "paid_at")
        assert abs((dt - (timezone.now() + timedelta(minutes=delta_min))).total_seconds()) < 90, raw
        future = dt > timezone.now() + MIs.CLOCK_SKEW
        assert future is (not ok), raw


def test_future_payment_date_is_refused_in_persian(user):
    from apps.orders import manual as MIs

    from apps.accounts.models import Staff

    boss_staff = Staff.objects.create(username="mi-boss", is_superadmin=True)
    when = _tehran(timezone.now() + timedelta(hours=2))
    with pytest.raises(MIs.ManualInvoiceError) as exc:
        MIs.create_paid(user, boss_staff, {"title": "x", "amount": "1000", "method": "cash",
                                           "paid_at": f"{when.date().isoformat()}T{when.hour:02d}:{when.minute:02d}:00"})
    assert exc.value.fa == "تاریخ پرداخت نمی‌تواند در آینده باشد"


def test_ledger_today_is_the_tehran_date(monkeypatch):
    from datetime import datetime, timezone as dt_tz

    from apps.agency import ledger

    late = datetime(2026, 11, 5, 22, 0, tzinfo=dt_tz.utc)               # 01:30 on Nov 6 in Tehran
    monkeypatch.setattr(timezone, "now", lambda: late)
    assert ledger.today().isoformat() == "2026-11-06"


# --- 3. renewal ----------------------------------------------------------------------------------------------------
@pytest.fixture
def cv_service(user, panel, custom):
    svc = Service.objects.create(user=user, panel=panel, panel_username="bahram_Tc", current_plan=custom,
                                 status=ServiceStatus.ACTIVE, subscription_url=f"{BASE}/sub/x", data_limit=200 * GB,
                                 data_used=10 * GB, expire_at=timezone.now() + timedelta(days=8), source="import")
    Order.objects.create(user=user, service=svc, plan=custom, type=OrderType.IMPORTED, status=OrderStatus.COMPLETED,
                         amount=0, amount_unique=0, unique_expire_at=timezone.now())
    return svc


def test_custom_volume_service_renews_with_its_last_volume(user, cv_service, custom, plan, django_capture_on_commit_callbacks):
    info = _api(user).get(f"/api/v1/services/{cv_service.id}/renew-info/").json()
    assert info["can_renew"] and not info["needs_plan"] and info["plan"]["id"] == custom.id     # CT-12 case
    assert info["last_gb"] == 200 and {p["id"] for p in info["plans"]} >= {custom.id, plan.id}
    r = _api(user).post("/api/v1/orders/", {"plan": custom.id, "type": "renew", "service": cv_service.id,
                                            "custom_volume_gb": 120}, format="json")
    assert r.status_code == 201, r.content
    order = Order.objects.get(pk=r.json()["order"]["id"])
    assert order.custom_volume_gb == 120 and order.amount == custom.price_for_volume(120)
    pay = Payment.objects.create(order=order, amount=order.amount_unique, status=PaymentStatus.PENDING)
    with django_capture_on_commit_callbacks(execute=True):
        approve_payment(pay.id)
    sr = ScheduledRenewal.objects.get(service=cv_service)
    assert sr.data_limit == 120 * GB
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"})
        rsps.add(responses.PUT, f"{BASE}/api/user/bahram_Tc", json={"username": "bahram_Tc"})
        rsps.add(responses.POST, f"{BASE}/api/user/bahram_Tc/reset", json={})
        rsps.add(responses.GET, f"{BASE}/api/user/bahram_Tc", json={
            "username": "bahram_Tc", "subscription_url": f"{BASE}/sub/x", "used_traffic": 0, "status": "active",
            "data_limit": 120 * GB, "expire": (timezone.now() + timedelta(days=38)).isoformat()})
        apply_scheduled_renewal(sr.id)
        put = [c for c in rsps.calls if c.request.method == "PUT"][0]
    assert json.loads(put.request.body)["data_limit"] == 120 * GB
    # next time: the 120 GB bought last is pre-filled
    assert _api(user).get(f"/api/v1/services/{cv_service.id}/renew-info/").json()["last_gb"] == 120


def test_a_retired_plan_renews_only_when_staff_mark_it(user, panel, plan):
    svc = Service.objects.create(user=user, panel=panel, panel_username="ret_acc", current_plan=plan,
                                 status=ServiceStatus.ACTIVE, subscription_url=f"{BASE}/sub/r")
    plan.is_active = False
    plan.save()
    info = _api(user).get(f"/api/v1/services/{svc.id}/renew-info/").json()
    assert info["plan"] is None and info["needs_plan"]
    with pytest.raises(OrderError):
        create_order(user=user, plan_id=plan.id, order_type=OrderType.RENEW, service_id=svc.id)
    plan.renewable_when_inactive = True
    plan.save()
    info = _api(user).get(f"/api/v1/services/{svc.id}/renew-info/").json()
    assert info["plan"]["id"] == plan.id and not info["needs_plan"]
    r = _api(user).post("/api/v1/orders/", {"plan": plan.id, "type": "renew", "service": svc.id}, format="json")
    assert r.status_code == 201, r.content
    other = User.objects.create_user("newbie", "Str0ngPass!")       # still not for sale as a new service
    with pytest.raises(OrderError):
        create_order(user=other, plan_id=plan.id, requested_account_name="newbie_1")


def test_bot_custom_volume_renewal_one_tap(monkeypatch, user, cv_service, custom):
    from apps.telegram.bot import sales_bot
    from apps.telegram.tests.test_bot_gate import TG, FakeBot, _msg

    monkeypatch.setattr(sales_bot, "close_old_connections", lambda: None)
    bot = FakeBot()
    sales_bot._register(bot)
    user.telegram_id, user.terms_accepted_at = TG, timezone.now()
    user.save()
    sent = bot.click(f"s:{cv_service.id}:rn")
    datas = [b.callback_data for _, m in sent for row in (getattr(m, "keyboard", None) or []) for b in row]
    assert f"rg:{cv_service.id}:{custom.id}:200" in datas
    assert "این سرویس پلن تمدید ندارد" not in " ".join(t or "" for t, _ in sent)
    # «تغییر حجم» asks the GB, typed in Persian digits
    bot.click(f"rn:{cv_service.id}:{custom.id}")
    bot.feed(_msg(text="۸۰"))
    o = Order.objects.get(type=OrderType.RENEW)
    assert o.custom_volume_gb == 80 and o.service_id == cv_service.id and o.amount == custom.price_for_volume(80)


def test_backfill_sets_the_plan_from_the_last_paid_order(user, panel, plan):
    import importlib

    from django.apps import apps as live

    svc = Service.objects.create(user=user, panel=panel, panel_username="noplan_1")
    Order.objects.create(user=user, service=svc, plan=plan, type=OrderType.NEW, status=OrderStatus.COMPLETED,
                         amount=1, amount_unique=1, unique_expire_at=timezone.now(), requested_account_name="noplan_1")
    bare = Service.objects.create(user=user, panel=panel, panel_username="noplan_2")
    mig = importlib.import_module("apps.panel.migrations.0007_backfill_service_plan")
    mig.forward(live, None)
    svc.refresh_from_db(); bare.refresh_from_db()
    assert svc.current_plan_id == plan.id and bare.current_plan_id is None
