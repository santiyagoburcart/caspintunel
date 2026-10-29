"""Renewal always runs on the SAME PasarGuard account and subscription link — with the
service's own plan, with a changed plan, or for a service linked manually without a plan.
No account-name step, never a new panel account."""
import json
from datetime import timedelta
from decimal import Decimal

import pytest
import responses
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Staff, User
from apps.common.models import AuditLog
from apps.orders.models import Order, OrderType, ScheduledRenewal
from apps.orders.services import OrderError, create_order, renewable_plan, renewal_plans
from apps.panel.models import Panel, Service, ServiceStatus
from apps.panel.services import apply_scheduled_renewal
from apps.payments_sms.models import Payment, PaymentStatus
from apps.payments_sms.services import approve_payment
from apps.plans.models import Plan, PlanType

pytestmark = pytest.mark.django_db
BASE = "https://panel.test"
GB = 1024 ** 3
SUB = f"{BASE}/sub/keep-this-link/"
ACC = "hasti_acc"


@pytest.fixture
def panel():
    return Panel.objects.create(name="P", base_url=BASE, admin_username="a", admin_password_enc="p")


@pytest.fixture
def plans(panel):
    a = Plan.objects.create(panel=panel, name_fa="پایه", name_en="Basic", price=Decimal("100000"),
                            data_limit=50 * GB, duration_days=30)
    b = Plan.objects.create(panel=panel, name_fa="طلایی", name_en="Gold", price=Decimal("300000"),
                            data_limit=200 * GB, duration_days=30)
    custom = Plan.objects.create(panel=panel, name_fa="دلخواه", price=Decimal("0"), type=PlanType.CUSTOM_VOLUME,
                                 price_per_gb=Decimal("5000"), min_gb=10, max_gb=500, duration_days=30)
    return a, b, custom


@pytest.fixture
def user():
    return User.objects.create_user("hasti", "Str0ngPass!", phone="09121112233")


def _service(user, panel, plan):
    return Service.objects.create(user=user, panel=panel, panel_username=ACC, current_plan=plan,
                                  status=ServiceStatus.ACTIVE, subscription_url=SUB, data_limit=20 * GB,
                                  data_used=19 * GB, expire_at=timezone.now() + timedelta(days=2), source="import")


def _api(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def _pay(order, django_capture_on_commit_callbacks):
    pay = Payment.objects.create(order=order, amount=order.amount_unique, status=PaymentStatus.PENDING)
    with django_capture_on_commit_callbacks(execute=True):
        approve_payment(pay.id)
    order.refresh_from_db()
    return order


def _panel_mocks(rsps, plan):
    rsps.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"})
    rsps.add(responses.PUT, f"{BASE}/api/user/{ACC}", json={"username": ACC})
    rsps.add(responses.POST, f"{BASE}/api/user/{ACC}/reset", json={})
    rsps.add(responses.GET, f"{BASE}/api/user/{ACC}", json={
        "username": ACC, "subscription_url": SUB, "used_traffic": 0, "status": "active",
        "data_limit": plan.data_limit, "expire": (timezone.now() + timedelta(days=32)).isoformat()})


def _apply_and_check(service, plan):
    """apply the paid renewal: only PUT / reset / GET on the same username, never a create"""
    sr = ScheduledRenewal.objects.get(service=service)
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        _panel_mocks(rsps, plan)
        apply_scheduled_renewal(sr.id)
        calls = [(c.request.method, c.request.url, c.request.body) for c in rsps.calls]
    assert not any(u.endswith("/api/user") for _, u, _ in calls)           # never creates an account
    puts = [(u, body) for m, u, body in calls if m == "PUT"]
    assert [u for u, _ in puts] == [f"{BASE}/api/user/{ACC}"]               # the same username
    assert json.loads(puts[0][1])["data_limit"] == plan.data_limit
    service.refresh_from_db()
    assert service.panel_username == ACC and service.subscription_url == SUB
    assert service.current_plan_id == plan.id
    assert Service.objects.filter(user=service.user).count() == 1
    return service


def test_renew_with_the_same_plan(user, panel, plans, django_capture_on_commit_callbacks):
    a, _, _ = plans
    svc = _service(user, panel, a)
    info = _api(user).get(f"/api/v1/services/{svc.id}/renew-info/").json()
    assert info["can_renew"] and info["plan"]["id"] == a.id and not info["needs_plan"]
    assert info["service"]["panel_username"] == ACC

    r = _api(user).post("/api/v1/orders/", {"plan": a.id, "type": "renew", "service": svc.id}, format="json")
    assert r.status_code == 201, r.content
    order = Order.objects.get(pk=r.json()["order"]["id"])
    assert order.type == OrderType.RENEW and order.service_id == svc.id and not order.requested_account_name
    assert order.amount == Decimal("100000")
    _pay(order, django_capture_on_commit_callbacks)
    _apply_and_check(svc, a)


def test_renew_with_a_plan_change(user, panel, plans, django_capture_on_commit_callbacks):
    a, b, _ = plans
    svc = _service(user, panel, a)
    info = _api(user).get(f"/api/v1/services/{svc.id}/renew-info/").json()
    assert {p["id"] for p in info["plans"]} == {a.id, b.id}          # custom volume is not a renewal plan

    r = _api(user).post(f"/api/v1/services/{svc.id}/renew/", {"plan": b.id}, format="json")
    assert r.status_code == 201, r.content
    order = Order.objects.get(pk=r.json()["order"]["id"])
    assert order.plan_id == b.id and order.service_id == svc.id and order.amount == Decimal("300000")
    svc.refresh_from_db()
    assert svc.current_plan_id == a.id                    # unchanged until paid
    _pay(order, django_capture_on_commit_callbacks)
    svc.refresh_from_db()
    assert svc.current_plan_id == b.id                    # plan updated after payment
    assert AuditLog.objects.filter(action="service.plan_changed", target_id=svc.id,
                                   detail__via="renewal").exists()
    _apply_and_check(svc, b)


def test_renew_a_planless_manually_linked_service(user, panel, plans, django_capture_on_commit_callbacks):
    a, b, _ = plans
    svc = _service(user, panel, None)
    info = _api(user).get(f"/api/v1/services/{svc.id}/renew-info/").json()
    assert info["can_renew"] and info["plan"] is None and info["needs_plan"]
    assert info["message"] and len(info["plans"]) == 2
    # the one-tap endpoint needs a plan here, it never falls back to a new purchase
    r = _api(user).post(f"/api/v1/services/{svc.id}/renew/", {}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "needs_plan"

    r = _api(user).post("/api/v1/orders/", {"plan": b.id, "type": "renew", "service": svc.id}, format="json")
    assert r.status_code == 201, r.content
    order = _pay(Order.objects.get(pk=r.json()["order"]["id"]), django_capture_on_commit_callbacks)
    svc.refresh_from_db()
    assert svc.current_plan_id == b.id
    _apply_and_check(svc, b)
    assert renewable_plan(svc) == b                        # next time: one tap
    assert order.requested_account_name in (None, "")


def test_discount_code_still_applies_to_a_renewal(user, panel, plans):
    from apps.crm.models import DiscountCode

    a, _, _ = plans
    svc = _service(user, panel, a)
    DiscountCode.objects.create(code="RENEW10", kind="campaign", discount_type="percent", percent=10,
                                applies_to="both", is_active=True)
    q = _api(user).post("/api/v1/orders/quote/", {"plan": a.id, "type": "renew", "service": svc.id,
                                                  "discount_code": "RENEW10"}, format="json")
    assert q.status_code == 200, q.content
    assert Decimal(str(q.json()["final"])) == Decimal("90000")


def test_custom_volume_plan_and_other_panels_are_refused_for_renewal(user, panel, plans):
    a, _, custom = plans
    svc = _service(user, panel, None)
    with pytest.raises(OrderError):
        create_order(user=user, plan_id=custom.id, order_type=OrderType.RENEW, service_id=svc.id,
                     custom_volume_gb=50)
    other = Panel.objects.create(name="Q", base_url="https://q.test", admin_username="a", admin_password_enc="p")
    foreign = Plan.objects.create(panel=other, name_fa="x", price=Decimal("1"), data_limit=GB, duration_days=1)
    assert foreign not in renewal_plans(svc)
    r = _api(user).post(f"/api/v1/services/{svc.id}/renew/", {"plan": foreign.id}, format="json")
    assert r.status_code == 400


# --- staff: set / change the plan, «بدون پلن» filter ----------------------------------
def _staff_client():
    s = Staff(username="boss", is_superadmin=True)
    s.set_password("x-Str0ng!pass")
    s.save()
    c = APIClient()
    c.force_authenticate(s)
    return c, s


def test_staff_sets_the_plan_without_touching_pasarguard(user, panel, plans):
    a, b, _ = plans
    svc = _service(user, panel, None)
    c, _ = _staff_client()
    lst = c.get("/api/v1/admin/services/?filter=no_plan").json()
    assert [r["id"] for r in lst["results"]] == [svc.id] and lst["results"][0]["plan_id"] is None
    assert lst["stats"]["no_plan"] == 1
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"})
        rsps.add(responses.GET, f"{BASE}/api/user/{ACC}", json={"username": ACC, "status": "active"})
        r = c.patch(f"/api/v1/admin/services/{svc.id}/", {"plan": a.id}, format="json")
        assert not any(x.request.method in ("PUT", "POST") and "/api/user" in x.request.url for x in rsps.calls)
    assert r.status_code == 200, r.content
    assert r.json()["plan_id"] == a.id and r.json()["panel_raw"]["username"] == ACC
    svc.refresh_from_db()
    assert svc.current_plan_id == a.id
    log = AuditLog.objects.get(action="service.plan_changed", target_id=svc.id)
    assert log.detail == {"old_plan": None, "plan": a.id, "via": "staff"} and log.staff_label == "boss"
    assert c.get("/api/v1/admin/services/?filter=no_plan").json()["results"] == []
    # clear it again / a plan from another panel is refused
    other = Panel.objects.create(name="Q", base_url="https://q.test", admin_username="a", admin_password_enc="p")
    foreign = Plan.objects.create(panel=other, name_fa="x", price=Decimal("1"), data_limit=GB, duration_days=1)
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"})
        rsps.add(responses.GET, f"{BASE}/api/user/{ACC}", json={"username": ACC})
        assert c.patch(f"/api/v1/admin/services/{svc.id}/", {"plan": foreign.id}, format="json").status_code == 400
        assert c.patch(f"/api/v1/admin/services/{svc.id}/", {"plan": None}, format="json").status_code == 200
    svc.refresh_from_db()
    assert svc.current_plan_id is None


def test_link_existing_account_with_a_plan(user, panel, plans):
    a, _, _ = plans
    c, _ = _staff_client()
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"})
        rsps.add(responses.GET, f"{BASE}/api/user/linked_one", json={
            "username": "linked_one", "status": "active", "subscription_url": "/sub/x", "admin": {"username": "a"}})
        r = c.post("/api/v1/admin/services/link/", {"panel": panel.id, "panel_username": "linked_one",
                                                   "user": user.id, "plan": a.id}, format="json")
    assert r.status_code == 201, r.content
    assert Service.objects.get(panel_username="linked_one").current_plan_id == a.id


# --- bot ---------------------------------------------------------------------------
@pytest.fixture
def bot(monkeypatch):
    from apps.telegram.bot import sales_bot
    from apps.telegram.tests.test_bot_gate import FakeBot

    monkeypatch.setattr(sales_bot, "close_old_connections", lambda: None)
    b = FakeBot()
    sales_bot._register(b)
    return b


def _buttons(sent):
    out = []
    for _, markup in sent:
        for row in getattr(markup, "keyboard", []) or []:
            for btn in row:
                out.append((getattr(btn, "text", ""), getattr(btn, "callback_data", None)))
    return out


def _bot_user(user):
    from apps.telegram.tests.test_bot_gate import TG

    user.telegram_id = TG
    user.terms_accepted_at = timezone.now()
    user.save()
    return TG


def test_bot_renew_same_plan_in_one_tap(bot, user, panel, plans):
    a, b, _ = plans
    _bot_user(user)
    svc = _service(user, panel, a)
    sent = bot.click(f"s:{svc.id}:rn")
    text = sent[-1][0]
    assert ACC in text and "همین اکانت" in text and "100,000" in text
    btns = _buttons(sent)
    assert (f"rn:{svc.id}:{a.id}") in [d for _, d in btns]
    assert (f"s:{svc.id}:rnp") in [d for _, d in btns]
    sent = bot.click(f"rn:{svc.id}:{a.id}")
    order = Order.objects.get(user=user)
    assert order.type == OrderType.RENEW and order.service_id == svc.id and order.plan_id == a.id
    assert not any("نام" in t and "اکانت" in t and "وارد" in t for t, _ in sent)    # no account-name step
    from apps.telegram.bot.sales_bot import get_state

    assert get_state(user.telegram_id).get("awaiting") != "name"


def test_bot_change_plan_lists_renewal_plans_on_the_same_account(bot, user, panel, plans):
    a, b, custom = plans
    _bot_user(user)
    svc = _service(user, panel, a)
    datas = [d for _, d in _buttons(bot.click(f"s:{svc.id}:rnp"))]
    assert f"rn:{svc.id}:{a.id}" in datas and f"rn:{svc.id}:{b.id}" in datas
    assert f"rn:{svc.id}:{custom.id}" not in datas
    bot.click(f"rn:{svc.id}:{b.id}")
    order = Order.objects.get(user=user)
    assert order.plan_id == b.id and order.service_id == svc.id and order.type == OrderType.RENEW


def test_bot_planless_service_shows_the_plan_list_with_a_note(bot, user, panel, plans):
    a, b, _ = plans
    _bot_user(user)
    svc = _service(user, panel, None)
    sent = bot.click(f"s:{svc.id}:rn")
    assert "پلن تمدید ندارد" in sent[-1][0] and "همین اکانت" in sent[-1][0]
    datas = [d for _, d in _buttons(sent)]
    assert f"rn:{svc.id}:{a.id}" in datas and f"rn:{svc.id}:{b.id}" in datas
    bot.click(f"rn:{svc.id}:{a.id}")
    assert Order.objects.get(user=user).service_id == svc.id
