"""/admin/services/ — the standalone sold-services admin page's API surface:
list/filter/search, status change, reset, revoke, manual creation, and the
services.manage permission gate."""
from decimal import Decimal

import pytest
import responses

from apps.accounts.models import User
from apps.adminpanel.tests.conftest import make_staff
from apps.panel.models import Panel, Service, ServiceStatus
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db
BASE = "https://panel.test"


@pytest.fixture
def panel():
    return Panel.objects.create(name="T", base_url=BASE, admin_username="adm",
                                admin_password_enc="pw", is_active=True)


@pytest.fixture
def plan(panel):
    return Plan.objects.create(panel=panel, name_fa="30d", price=Decimal("100000"), duration_days=30)


@pytest.fixture
def cust():
    return User.objects.create_user("cust1", "Str0ngPass!")


def _token(rsps):
    rsps.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"}, status=200)


def test_list_requires_monitoring_view(staff_client, perms, panel, plan, cust):
    viewer = make_staff("viewer", ["monitoring.view"], perms)
    Service.objects.create(user=cust, panel=panel, panel_username="svc-1", current_plan=plan)
    r = staff_client(viewer).get("/api/v1/admin/services/")
    assert r.status_code == 200
    assert r.data["stats"]["total"] == 1


def test_list_filters_by_status_and_search(staff_client, perms, panel, plan, cust):
    Service.objects.create(user=cust, panel=panel, panel_username="alpha", current_plan=plan,
                           status=ServiceStatus.ACTIVE)
    Service.objects.create(user=cust, panel=panel, panel_username="beta", current_plan=plan,
                           status=ServiceStatus.DISABLED)
    viewer = make_staff("viewer2", ["monitoring.view"], perms)
    c = staff_client(viewer)

    r = c.get("/api/v1/admin/services/?filter=active")
    names = [row["panel_username"] for row in r.data["results"]]
    assert names == ["alpha"]

    r2 = c.get("/api/v1/admin/services/?search=bet")
    names2 = [row["panel_username"] for row in r2.data["results"]]
    assert names2 == ["beta"]


def test_status_change_requires_services_manage(staff_client, perms, panel, plan, cust):
    svc = Service.objects.create(user=cust, panel=panel, panel_username="svc-2", current_plan=plan,
                                 status=ServiceStatus.ACTIVE)
    viewer_only = make_staff("viewer3", ["monitoring.view"], perms)
    r = staff_client(viewer_only).post(f"/api/v1/admin/services/{svc.id}/status/", {"status": "disabled"})
    assert r.status_code == 403


@responses.activate
def test_status_change_end_to_end(staff_client, perms, panel, plan, cust):
    svc = Service.objects.create(user=cust, panel=panel, panel_username="svc-3", current_plan=plan,
                                 status=ServiceStatus.ACTIVE)
    manager = make_staff("mgr", ["monitoring.view", "services.manage"], perms)
    _token(responses)
    responses.add(responses.PUT, f"{BASE}/api/user/svc-3", json={"username": "svc-3"}, status=200)
    responses.add(responses.GET, f"{BASE}/api/user/svc-3",
                  json={"username": "svc-3", "status": "on_hold"}, status=200)

    r = staff_client(manager).post(f"/api/v1/admin/services/{svc.id}/status/", {"status": "on_hold"})
    assert r.status_code == 200, r.data
    assert r.data["status"] == "on_hold"


@responses.activate
def test_manual_create_end_to_end(staff_client, perms, panel, plan, cust):
    manager = make_staff("mgr2", ["monitoring.view", "services.manage"], perms)
    _token(responses)
    responses.add(responses.POST, f"{BASE}/api/user",
                  json={"username": "brandnew", "status": "on_hold", "subscription_url": "/s/n/"},
                  status=200)

    r = staff_client(manager).post("/api/v1/admin/services/", {
        "user": cust.id, "plan": plan.id, "account_name": "brandnew",
    }, format="json")
    assert r.status_code == 201, r.data
    assert r.data["panel_username"] == "brandnew"
    assert r.data["panel_name"] == "T"

    svc = Service.objects.get(panel_username="brandnew")
    assert svc.source == "admin"


def test_manual_create_requires_services_manage(staff_client, perms, panel, plan, cust):
    viewer_only = make_staff("viewer4", ["monitoring.view"], perms)
    r = staff_client(viewer_only).post("/api/v1/admin/services/", {
        "user": cust.id, "plan": plan.id, "account_name": "x",
    }, format="json")
    assert r.status_code == 403
