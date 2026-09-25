"""PATCH /admin/services/<id>/ — full service edit: panel first, then our DB."""
import json
from decimal import Decimal

import pytest
import responses

from apps.accounts.models import User
from apps.adminpanel.tests.conftest import make_staff
from apps.common.models import AuditLog
from apps.panel.models import Panel, Service, ServiceStatus
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db
BASE = "https://panel.test"
GB = 1024 ** 3


@pytest.fixture
def svc():
    panel = Panel.objects.create(name="T", base_url=BASE, admin_username="adm", admin_password_enc="pw", is_active=True)
    plan = Plan.objects.create(panel=panel, name_fa="30d", price=Decimal("1"), duration_days=30)
    user = User.objects.create_user("cust", "Str0ngPass!")
    return Service.objects.create(user=user, panel=panel, panel_username="wewewe", current_plan=plan,
                                  status=ServiceStatus.ACTIVE, data_limit=50 * GB, alert_vol_sent=True)


def _panel(rsps, after: dict):
    rsps.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"})
    rsps.add(responses.PUT, f"{BASE}/api/user/wewewe", json={"username": "wewewe"})
    rsps.add(responses.GET, f"{BASE}/api/user/wewewe",
             json={"username": "wewewe", "used_traffic": 3 * GB, "subscription_url": "/sub/x", **after})


def _sent(rsps):
    return json.loads(next(c.request.body for c in rsps.calls if c.request.method == "PUT"))


def test_edit_writes_panel_then_mirrors(staff_client, superadmin, svc):
    with responses.RequestsMock() as rsps:
        _panel(rsps, {"status": "active", "data_limit": 100 * GB, "expire": "2026-10-02T20:29:59+00:00",
                      "group_ids": [5, 8], "note": "vip"})
        r = staff_client(superadmin).patch(f"/api/v1/admin/services/{svc.id}/", {
            "status": "active", "data_limit_gb": "100", "expire_date": "2026-10-02",
            "group_ids": [5, 8], "note": "vip",
        }, format="json")
        sent = _sent(rsps)
    assert r.status_code == 200, r.data
    assert sent["data_limit"] == 100 * GB and sent["group_ids"] == [5, 8] and sent["note"] == "vip"
    assert sent["expire"].startswith("2026-10-02T23:59:59+03:30")          # end of day, Tehran
    svc.refresh_from_db()
    assert svc.data_limit == 100 * GB and svc.data_used == 3 * GB
    assert svc.expire_at is not None and svc.alert_vol_sent is False
    assert r.data["panel_raw"]["note"] == "vip"
    assert AuditLog.objects.filter(action="service.edited", target_id=svc.id).exists()


def test_only_sent_fields_are_changed(staff_client, superadmin, svc):
    with responses.RequestsMock() as rsps:
        _panel(rsps, {"status": "active", "data_limit": 50 * GB, "note": "hello"})
        r = staff_client(superadmin).patch(f"/api/v1/admin/services/{svc.id}/", {"note": "hello"}, format="json")
        assert _sent(rsps) == {"note": "hello"}
    assert r.status_code == 200


def test_on_hold_needs_and_sends_duration(staff_client, superadmin, svc):
    r = staff_client(superadmin).patch(f"/api/v1/admin/services/{svc.id}/", {"status": "on_hold"}, format="json")
    assert r.status_code == 400                                             # no duration known
    with responses.RequestsMock() as rsps:
        _panel(rsps, {"status": "on_hold", "on_hold_expire_duration": 30 * 86400, "data_limit": 50 * GB})
        r = staff_client(superadmin).patch(f"/api/v1/admin/services/{svc.id}/",
                                           {"status": "on_hold", "on_hold_days": 30}, format="json")
        sent = _sent(rsps)
    assert r.status_code == 200
    assert sent == {"status": "on_hold", "on_hold_expire_duration": 30 * 86400, "expire": None}
    svc.refresh_from_db()
    assert svc.status == ServiceStatus.ON_HOLD and svc.on_hold_duration == 30 * 86400


def test_unlimited_and_no_expiry(staff_client, superadmin, svc):
    with responses.RequestsMock() as rsps:
        _panel(rsps, {"status": "active", "data_limit": 0, "expire": None})
        r = staff_client(superadmin).patch(f"/api/v1/admin/services/{svc.id}/",
                                           {"data_limit_gb": 0, "expire_date": None}, format="json")
        assert _sent(rsps) == {"data_limit": 0, "expire": None}
    assert r.status_code == 200
    svc.refresh_from_db()
    assert svc.data_limit == 0 and svc.expire_at is None


def test_panel_failure_leaves_db_untouched(staff_client, superadmin, svc):
    with responses.RequestsMock() as rsps:
        rsps.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"})
        rsps.add(responses.PUT, f"{BASE}/api/user/wewewe", json={"detail": "boom"}, status=500)
        r = staff_client(superadmin).patch(f"/api/v1/admin/services/{svc.id}/", {"data_limit_gb": 1}, format="json")
    assert r.status_code == 502
    svc.refresh_from_db()
    assert svc.data_limit == 50 * GB


def test_edit_requires_services_manage(staff_client, perms, svc):
    viewer = make_staff("viewer", ["monitoring.view"], perms)
    r = staff_client(viewer).patch(f"/api/v1/admin/services/{svc.id}/", {"note": "x"}, format="json")
    assert r.status_code == 403


def test_bad_input_rejected(staff_client, superadmin, svc):
    c = staff_client(superadmin)
    assert c.patch(f"/api/v1/admin/services/{svc.id}/", {"status": "expired"}, format="json").status_code == 400
    assert c.patch(f"/api/v1/admin/services/{svc.id}/", {"data_limit_gb": -1}, format="json").status_code == 400
