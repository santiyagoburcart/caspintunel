"""Phase 4 — link an EXISTING panel account to one of our users, and the
editable device (HWID) limit on the service edit page."""
import json
from decimal import Decimal

import pytest
import responses

from apps.accounts.models import User
from apps.adminpanel.tests.conftest import make_staff
from apps.common.models import AuditLog
from apps.orders.models import Order, OrderStatus, OrderType
from apps.panel.models import Panel, Service, ServiceStatus
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db
BASE = "https://panel.test"
GB = 1024 ** 3

PANEL_USER = {
    "username": "OldCustomer", "status": "active", "used_traffic": 7 * GB, "data_limit": 100 * GB,
    "expire": "2026-12-01T00:00:00+00:00", "subscription_url": "/sub/abc", "hwid_limit": 3,
}


@pytest.fixture
def ctx():
    panel = Panel.objects.create(name="P1", base_url=BASE, admin_username="a", admin_password_enc="p")
    other_panel = Panel.objects.create(name="P2", base_url="https://other.test", admin_username="a",
                                       admin_password_enc="p")
    plan = Plan.objects.create(panel=panel, name_fa="p", price=Decimal("1"), duration_days=30)
    foreign_plan = Plan.objects.create(panel=other_panel, name_fa="x", price=Decimal("1"), duration_days=30)
    owner = User.objects.create_user("owner", "Str0ngPass!")
    cust = User.objects.create_user("cust", "Str0ngPass!")
    taken = Service.objects.create(user=owner, panel=panel, panel_username="taken1", status=ServiceStatus.ACTIVE)
    return {"panel": panel, "plan": plan, "foreign_plan": foreign_plan, "cust": cust, "taken": taken}


def _token(rsps):
    rsps.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"})


def test_search_shows_live_rows_and_linked_flag(staff_client, superadmin, ctx):
    with responses.RequestsMock() as rsps:
        _token(rsps)
        rsps.add(responses.GET, f"{BASE}/api/users", json={"users": [
            PANEL_USER, {"username": "TAKEN1", "status": "disabled", "used_traffic": 0, "data_limit": 0},
        ], "total": 2})
        r = staff_client(superadmin).get(f"/api/v1/admin/services/panel-users/?panel={ctx['panel'].id}&search=o")
        assert "search=o" in rsps.calls[-1].request.url and "limit=20" in rsps.calls[-1].request.url
    assert r.status_code == 200, r.data
    rows = {x["username"]: x for x in r.data["results"]}
    assert rows["OldCustomer"]["linked"] is None and rows["OldCustomer"]["used_traffic"] == 7 * GB
    assert rows["TAKEN1"]["linked"]["username"] == "owner"                 # case-insensitive match
    assert rows["TAKEN1"]["linked"]["service_id"] == ctx["taken"].id


def test_link_creates_service_and_imported_order_without_touching_panel(staff_client, superadmin, ctx):
    with responses.RequestsMock() as rsps:
        _token(rsps)
        rsps.add(responses.GET, f"{BASE}/api/user/oldcustomer", json=PANEL_USER)
        r = staff_client(superadmin).post("/api/v1/admin/services/link/", {
            "panel": ctx["panel"].id, "panel_username": "oldcustomer", "user": ctx["cust"].id,
            "plan": ctx["plan"].id,
        }, format="json")
        assert {c.request.method for c in rsps.calls} == {"POST", "GET"}    # token + read only
    assert r.status_code == 201, r.data
    svc = Service.objects.get(pk=r.data["id"])
    assert svc.user == ctx["cust"] and svc.panel_username == "OldCustomer"   # the panel's spelling
    assert svc.status == ServiceStatus.ACTIVE and svc.data_used == 7 * GB and svc.data_limit == 100 * GB
    assert svc.subscription_url == f"{BASE}/sub/abc" and svc.device_limit == 3 and svc.current_plan == ctx["plan"]
    order = Order.objects.get(service=svc)
    assert order.type == OrderType.IMPORTED and order.status == OrderStatus.COMPLETED
    assert order.amount == 0 and order.plan == ctx["plan"] and not hasattr(order, "payment")
    assert AuditLog.objects.filter(action="service.linked_existing", target_id=svc.id).exists()


def test_link_without_plan(staff_client, superadmin, ctx):
    with responses.RequestsMock() as rsps:
        _token(rsps)
        rsps.add(responses.GET, f"{BASE}/api/user/OldCustomer", json=PANEL_USER)
        r = staff_client(superadmin).post("/api/v1/admin/services/link/", {
            "panel": ctx["panel"].id, "panel_username": "OldCustomer", "user": ctx["cust"].id,
        }, format="json")
    assert r.status_code == 201, r.data
    order = Order.objects.get(service_id=r.data["id"])
    assert order.plan is None and order.type == OrderType.IMPORTED
    # an imported order with no plan still renders in the purchase history
    hist = staff_client(superadmin).get(f"/api/v1/admin/users/{ctx['cust'].id}/orders/")
    assert hist.status_code == 200 and hist.data[0]["plan_name"] is None


def test_already_linked_is_blocked(staff_client, superadmin, ctx):
    r = staff_client(superadmin).post("/api/v1/admin/services/link/", {
        "panel": ctx["panel"].id, "panel_username": "Taken1", "user": ctx["cust"].id,
    }, format="json")                                                        # no panel call at all
    assert r.status_code == 409 and r.data["username"] == "owner"
    assert Service.objects.filter(panel_username__iexact="taken1").count() == 1


def test_link_guards(staff_client, superadmin, perms, ctx):
    c = staff_client(superadmin)
    # plan from another panel
    r = c.post("/api/v1/admin/services/link/", {"panel": ctx["panel"].id, "panel_username": "x",
                                               "user": ctx["cust"].id, "plan": ctx["foreign_plan"].id}, format="json")
    assert r.status_code == 400
    # not on the panel
    with responses.RequestsMock() as rsps:
        _token(rsps)
        rsps.add(responses.GET, f"{BASE}/api/user/ghost", json={"detail": "nf"}, status=404)
        r = c.post("/api/v1/admin/services/link/", {"panel": ctx["panel"].id, "panel_username": "ghost",
                                                   "user": ctx["cust"].id}, format="json")
    assert r.status_code == 404 and not Service.objects.filter(panel_username="ghost").exists()
    assert not Order.objects.filter(type=OrderType.IMPORTED).exists()
    # needs services.manage, for search too
    viewer = make_staff("viewer", ["monitoring.view"], perms)
    assert staff_client(viewer).get(f"/api/v1/admin/services/panel-users/?panel={ctx['panel'].id}").status_code == 403
    assert staff_client(viewer).post("/api/v1/admin/services/link/", {}, format="json").status_code == 403


def test_hwid_limit_is_editable(staff_client, superadmin, ctx):
    svc = ctx["taken"]
    c = staff_client(superadmin)
    with responses.RequestsMock() as rsps:
        _token(rsps)
        rsps.add(responses.PUT, f"{BASE}/api/user/taken1", json={})
        rsps.add(responses.GET, f"{BASE}/api/user/taken1", json={"username": "taken1", "status": "active", "hwid_limit": 2})
        r = c.patch(f"/api/v1/admin/services/{svc.id}/", {"hwid_limit": 2}, format="json")
        sent = json.loads(next(x.request.body for x in rsps.calls if x.request.method == "PUT"))
    assert r.status_code == 200, r.data
    assert sent == {"hwid_limit": 2}
    svc.refresh_from_db()
    assert svc.device_limit == 2

    with responses.RequestsMock() as rsps:                                  # empty = unlimited = 0
        rsps.add(responses.PUT, f"{BASE}/api/user/taken1", json={})
        rsps.add(responses.GET, f"{BASE}/api/user/taken1", json={"username": "taken1", "status": "active", "hwid_limit": 0})
        r = c.patch(f"/api/v1/admin/services/{svc.id}/", {"hwid_limit": None}, format="json")
        sent = json.loads(next(x.request.body for x in rsps.calls if x.request.method == "PUT"))
    assert r.status_code == 200 and sent == {"hwid_limit": 0}
    svc.refresh_from_db()
    assert svc.device_limit is None
    assert c.patch(f"/api/v1/admin/services/{svc.id}/", {"hwid_limit": -1}, format="json").status_code == 400
