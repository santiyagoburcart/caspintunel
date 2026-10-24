"""Account names must be free on the PasarGuard panel too, not only in our DB:
we never attach a customer to someone else's panel account (e.g. a reseller's
customer with the same name). Site + bot ask for another name; a paid order
whose name turned out to be taken waits for a new name; staff must choose
"link existing account" explicitly (and confirm another admin's account)."""
import json
from datetime import timedelta
from decimal import Decimal

import pytest
import responses
from django.utils import timezone

from apps.accounts.models import User
from apps.common.models import AuditLog
from apps.notifications.models import Notification
from apps.orders.models import Order, OrderStatus, OrderType
from apps.orders.services import OrderError, create_order, rename_paid_order
from apps.panel.exceptions import PanelNameTaken
from apps.panel.models import Panel, Service, ServiceStatus
from apps.panel.services import create_manual_service, provision_service
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db
BASE = "https://panel.test"
GB = 1024 ** 3


@pytest.fixture
def panel():
    return Panel.objects.create(name="T", base_url=BASE, admin_username="adm", admin_password_enc="pw", is_active=True)


@pytest.fixture
def plan(panel):
    return Plan.objects.create(panel=panel, name_fa="30d", price=Decimal("100000"), data_limit=50 * GB, duration_days=30)


@pytest.fixture
def cust():
    return User.objects.create_user("cust", "Str0ngPass!", telegram_id=4242)


def _token(rsps):
    rsps.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"})


def foreign(name, owner="Sajad", **kw):
    """someone else's account: made months ago by another admin, no caspintunel note"""
    return {"username": name, "status": "active", "used_traffic": GB, "data_limit": 2 * GB, "note": "",
            "created_at": "2026-05-27T14:08:12Z", "admin": {"username": owner}, "subscription_url": "/sub/x", **kw}


def created(payload, **kw):
    return {**payload, "status": payload.get("status", "on_hold"), "used_traffic": 0,
            "created_at": timezone.now().isoformat(), "admin": {"username": "adm"}, "subscription_url": "/sub/new", **kw}


# ------------------------------------------------------------------ before payment (site + bot share create_order)
@responses.activate
def test_order_refuses_a_name_that_exists_on_the_panel(cust, plan):
    _token(responses)
    responses.add(responses.GET, f"{BASE}/api/user/parsa", json=foreign("parsa"))
    responses.add(responses.GET, f"{BASE}/api/user/free1", json={"detail": "User not found"}, status=404)
    with pytest.raises(OrderError, match="already taken"):
        create_order(user=cust, plan_id=plan.id, requested_account_name="parsa")
    assert not Order.objects.exists()
    assert create_order(user=cust, plan_id=plan.id, requested_account_name="free1").requested_account_name == "free1"


@responses.activate
def test_site_api_returns_the_name_error(cust, plan):
    from rest_framework.test import APIClient

    _token(responses)
    responses.add(responses.GET, f"{BASE}/api/user/parsa", json=foreign("parsa"))
    c = APIClient()
    c.force_authenticate(cust)
    r = c.post("/api/v1/orders/", {"plan": plan.id, "type": "new", "requested_account_name": "parsa"}, format="json")
    assert r.status_code == 400 and "already taken" in json.dumps(r.data)


@responses.activate
def test_panel_unreachable_does_not_block_sales(cust, plan):
    import requests

    responses.add(responses.POST, f"{BASE}/api/admin/token", body=requests.ConnectionError("down"))
    assert create_order(user=cust, plan_id=plan.id, requested_account_name="ok1").status == OrderStatus.PENDING_PAYMENT


# ------------------------------------------------------------------ provisioning never adopts someone else's account
def _svc(cust, panel, plan, name, **kw):
    return Service.objects.create(user=cust, panel=panel, panel_username=name, current_plan=plan,
                                  status=ServiceStatus.PENDING, **kw)


@responses.activate
def test_provision_refuses_a_foreign_account_on_409(cust, panel, plan):
    svc = _svc(cust, panel, plan, "parsa")
    _token(responses)
    responses.add(responses.POST, f"{BASE}/api/user", json={"detail": "User already exists"}, status=409)
    responses.add(responses.GET, f"{BASE}/api/user/parsa", json=foreign("parsa"))
    with pytest.raises(PanelNameTaken) as ei:
        provision_service(svc.id, plan=plan)
    assert ei.value.owner == "Sajad"
    svc.refresh_from_db()
    assert svc.status == ServiceStatus.PENDING and not svc.subscription_url        # nothing copied from it
    assert not [c for c in responses.calls if c.request.method == "PUT"]           # never modified


@responses.activate
def test_provision_adopts_its_own_earlier_attempt(cust, panel, plan):
    svc = _svc(cust, panel, plan, "mine1")
    _token(responses)
    responses.add(responses.POST, f"{BASE}/api/user", json={"detail": "User already exists"}, status=409)
    responses.add(responses.GET, f"{BASE}/api/user/mine1",
                  json=created({"username": "mine1", "note": f"caspintunel#{svc.id}", "data_limit": 50 * GB}))
    provision_service(svc.id, plan=plan)
    svc.refresh_from_db()
    assert svc.subscription_url.endswith("/sub/new") and svc.status != ServiceStatus.PENDING


@responses.activate
def test_our_note_on_an_older_account_is_not_enough(cust, panel, plan):
    """IDs restart after a data reset: an old account with a reused note must not be adopted."""
    svc = _svc(cust, panel, plan, "old1")
    _token(responses)
    responses.add(responses.POST, f"{BASE}/api/user", json={"detail": "exists"}, status=409)
    responses.add(responses.GET, f"{BASE}/api/user/old1", json=foreign("old1", owner="adm", note=f"caspintunel#{svc.id}"))
    with pytest.raises(PanelNameTaken):
        provision_service(svc.id, plan=plan)


# ------------------------------------------------------------------ paid order + taken name → ask for another (site + bot)
@pytest.fixture
def paid_order(cust, plan):
    o = Order(user=cust, plan=plan, type=OrderType.NEW, requested_account_name="parsa", amount=100000,
              amount_unique=100300, unique_expire_at=timezone.now() + timedelta(hours=1), status=OrderStatus.PAID)
    o.sync_unique_lock()
    o.save()
    return o


@responses.activate
def test_paid_order_with_a_taken_name_waits_for_a_new_name(cust, panel, plan, paid_order, monkeypatch):
    from apps.orders import tasks

    sent = []

    class Bot:
        def send_message(self, chat, text, **kw):
            sent.append((chat, text, kw))

    monkeypatch.setattr("apps.telegram.config.sales_client", lambda: Bot())
    _token(responses)
    responses.add(responses.POST, f"{BASE}/api/user", json={"detail": "exists"}, status=409)
    responses.add(responses.GET, f"{BASE}/api/user/parsa", json=foreign("parsa"))
    assert tasks.fulfill_order(paid_order.id) == {"order": paid_order.id, "status": "needs_new_name"}
    paid_order.refresh_from_db()
    assert paid_order.status == OrderStatus.PAID and paid_order.needs_new_name and paid_order.service_id is None
    assert not Service.objects.filter(panel_username="parsa").exists()            # never linked
    assert AuditLog.objects.filter(action="order.account_name_taken", target_id=paid_order.id).exists()
    n = Notification.objects.get(target_user=cust)
    assert "parsa" in n.body and n.link == f"/checkout?order={paid_order.id}"
    chat, text, kw = sent[0]
    assert chat == 4242 and "parsa" in text and kw["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == f"nn:{paid_order.id}"
    # the self-healing retry leaves it alone
    Order.objects.filter(pk=paid_order.pk).update(updated_at=timezone.now() - timedelta(hours=1))
    calls = []
    monkeypatch.setattr(tasks.fulfill_order, "delay", lambda oid: calls.append(oid))
    tasks.retry_unfulfilled_orders()
    assert calls == []


@responses.activate
def test_customer_picks_a_new_name_on_the_site(cust, panel, plan, paid_order, monkeypatch):
    from rest_framework.test import APIClient

    from apps.orders import tasks

    Order.objects.filter(pk=paid_order.pk).update(needs_new_name=True)
    dispatched = []
    monkeypatch.setattr(tasks.fulfill_order, "delay", lambda oid: dispatched.append(oid))
    _token(responses)
    responses.add(responses.GET, f"{BASE}/api/user/santiyago", json=foreign("santiyago", owner="adm"))
    responses.add(responses.GET, f"{BASE}/api/user/parsa2", json={"detail": "nf"}, status=404)
    c = APIClient()
    c.force_authenticate(cust)
    url = f"/api/v1/orders/{paid_order.id}/account-name/"
    assert c.get(f"/api/v1/orders/{paid_order.id}/").data["needs_new_name"] is True
    r = c.post(url, {"requested_account_name": "santiyago"}, format="json")
    assert r.status_code == 400 and "already taken" in r.data["requested_account_name"][0]
    assert c.post(url, {"requested_account_name": "bad name!"}, format="json").status_code == 400
    r = c.post(url, {"requested_account_name": "parsa2"}, format="json")
    assert r.status_code == 200 and r.data["order"]["requested_account_name"] == "parsa2"
    assert r.data["order"]["needs_new_name"] is False
    # someone else's order / an order that doesn't need it
    other = User.objects.create_user("other", "Str0ngPass!")
    c.force_authenticate(other)
    assert c.post(url, {"requested_account_name": "x2"}, format="json").status_code == 404
    with pytest.raises(OrderError):
        rename_paid_order(Order.objects.get(pk=paid_order.pk), "again2")


# ------------------------------------------------------------------ staff: manual create + explicit link
@responses.activate
def test_manual_create_never_adopts_an_existing_panel_account(cust, panel, plan, staff_client, superadmin):
    _token(responses)
    responses.add(responses.GET, f"{BASE}/api/user/parsa", json=foreign("parsa"))
    with pytest.raises(PanelNameTaken):
        create_manual_service(user=cust, plan=plan, account_name="parsa")
    r = staff_client(superadmin).post("/api/v1/admin/services/", {
        "user": cust.id, "plan": plan.id, "account_name": "parsa"}, format="json")
    assert r.status_code == 409 and r.data["code"] == "exists_on_panel" and r.data["owner"] == "Sajad"
    assert not Service.objects.exists() and not Order.objects.exists()
    assert not [c for c in responses.calls if c.request.method == "POST" and c.request.url.endswith("/api/user")]


@responses.activate
def test_link_of_another_admins_account_needs_an_explicit_choice(cust, panel, staff_client, superadmin):
    _token(responses)
    responses.add(responses.GET, f"{BASE}/api/user/parsa", json=foreign("parsa"))
    responses.add(responses.GET, f"{BASE}/api/users", json={"users": [foreign("parsa"), foreign("mine", owner="adm")], "total": 2})
    c = staff_client(superadmin)
    rows = {x["username"]: x for x in c.get(f"/api/v1/admin/services/panel-users/?panel={panel.id}&search=").data["results"]}
    assert rows["parsa"]["owner"] == "Sajad" and rows["parsa"]["other_admin"] is True
    assert rows["mine"]["other_admin"] is False
    body = {"panel": panel.id, "panel_username": "parsa", "user": cust.id}
    r = c.post("/api/v1/admin/services/link/", body, format="json")
    assert r.status_code == 409 and r.data["code"] == "other_admin" and r.data["owner"] == "Sajad"
    assert not Service.objects.exists()
    r = c.post("/api/v1/admin/services/link/", {**body, "confirm_other_admin": True}, format="json")
    assert r.status_code == 201, r.data
    log = AuditLog.objects.get(action="service.linked_existing")
    assert log.detail["panel_owner"] == "Sajad" and log.detail["other_admin_confirmed"] is True
