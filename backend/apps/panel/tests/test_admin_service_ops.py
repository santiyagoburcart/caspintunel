"""Admin-triggered service operations: status change and manual (no-payment)
creation — the /admin/services/ page's per-row actions and "create manual
service" flow."""
from decimal import Decimal

import pytest
import responses

from apps.accounts.models import User
from apps.orders.models import Order, OrderStatus, OrderType
from apps.panel.exceptions import PanelError
from apps.panel.models import Panel, Service, ServiceStatus
from apps.panel.services import create_manual_service, set_service_status
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db
BASE = "https://panel.test"


@pytest.fixture
def panel():
    return Panel.objects.create(name="T", base_url=BASE, admin_username="adm",
                                admin_password_enc="pw", default_group_ids=[1, 2], is_active=True)


@pytest.fixture
def user():
    return User.objects.create_user("cust", "Str0ngPass!")


@pytest.fixture
def plan(panel):
    return Plan.objects.create(panel=panel, name_fa="30d", price=Decimal("100000"),
                               data_limit=50 * 1024**3, duration_days=30, group_ids=[1, 2])


def _token(rsps):
    rsps.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"}, status=200)


@responses.activate
def test_set_service_status_updates_panel_and_service(user, panel, plan):
    svc = Service.objects.create(user=user, panel=panel, panel_username="cust-1",
                                 current_plan=plan, status=ServiceStatus.ACTIVE)
    _token(responses)
    responses.add(responses.PUT, f"{BASE}/api/user/cust-1", json={"username": "cust-1"}, status=200)
    responses.add(responses.GET, f"{BASE}/api/user/cust-1",
                  json={"username": "cust-1", "status": "disabled"}, status=200)
    out = set_service_status(svc.id, "disabled")
    assert out.status == ServiceStatus.DISABLED


def test_set_service_status_rejects_unknown_status(user, panel, plan):
    svc = Service.objects.create(user=user, panel=panel, panel_username="cust-1", current_plan=plan)
    with pytest.raises(ValueError):
        set_service_status(svc.id, "bogus")


@responses.activate
def test_create_manual_service_creates_order_and_service(user, panel, plan):
    _token(responses)
    responses.add(responses.POST, f"{BASE}/api/user",
                  json={"username": "manual-1", "status": "on_hold", "subscription_url": "/s/m1/"},
                  status=200)
    svc = create_manual_service(user=user, plan=plan, account_name="manual-1")

    assert svc.panel_username == "manual-1"
    assert svc.user_id == user.id
    assert svc.current_plan_id == plan.id
    assert svc.source == "admin"
    assert svc.subscription_url == f"{BASE}/s/m1/"

    order = Order.objects.get(service=svc)
    assert order.type == OrderType.MANUAL
    assert order.status == OrderStatus.COMPLETED
    assert order.amount == 0
    assert order.amount_unique_lock is None  # completed orders never hold the unique-amount lock


@responses.activate
def test_create_manual_service_auto_generates_account_name(user, panel, plan):
    _token(responses)
    responses.add(responses.POST, f"{BASE}/api/user",
                  json={"username": "whatever", "status": "active"}, status=200)
    svc = create_manual_service(user=user, plan=plan)
    assert svc.panel_username.startswith("m_")
    assert len(svc.panel_username) == 10  # "m_" + 8 hex chars


def test_create_manual_service_rejects_taken_name(user, panel, plan):
    Service.objects.create(user=user, panel=panel, panel_username="taken", current_plan=plan)
    with pytest.raises(PanelError):
        create_manual_service(user=user, plan=plan, account_name="taken")


@responses.activate
def test_create_manual_service_rejects_plan_panel_mismatch(user, panel, plan):
    other = Panel.objects.create(name="Other", base_url="https://o.test",
                                 admin_username="a", admin_password_enc="p", is_active=True)
    with pytest.raises(PanelError):
        create_manual_service(user=user, plan=plan, panel=other, account_name="x")
