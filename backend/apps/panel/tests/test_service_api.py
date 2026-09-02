from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.panel.models import Panel, Service, ServiceStatus
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup():
    user = User.objects.create_user("cust", "Str0ngPass!")
    panel = Panel.objects.create(name="P", base_url="https://x", admin_username="a", admin_password_enc="p")
    plan = Plan.objects.create(name_fa="p", price=Decimal("1"))
    svc = Service.objects.create(
        user=user, panel=panel, panel_username="cust-1", current_plan=plan,
        status=ServiceStatus.ACTIVE, subscription_url="https://x/myac/tok/",
        data_limit=100, data_used=30, expire_at=timezone.now() + timezone.timedelta(days=12),
    )
    return user, svc


def test_service_list_is_scoped_to_owner(setup):
    user, svc = setup
    other = User.objects.create_user("mallory", "Str0ngPass!")
    client = APIClient()
    client.force_authenticate(other)
    assert client.get("/api/v1/services/").data["results"] == []

    client.force_authenticate(user)
    r = client.get("/api/v1/services/")
    row = r.data["results"][0]
    assert row["days_left"] == 12
    assert row["data_left"] == 70
    assert row["qr"].endswith(f"/api/v1/services/{svc.id}/qr/")


def test_qr_endpoint_returns_png(setup):
    user, svc = setup
    client = APIClient()
    client.force_authenticate(user)
    r = client.get(f"/api/v1/services/{svc.id}/qr/")
    assert r.status_code == 200
    assert r["Content-Type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


# --- on-hold -> active flip when the customer connects -------------------
import responses  # noqa: E402


@pytest.fixture
def onhold_setup():
    user = User.objects.create_user("hold", "Str0ngPass!")
    panel = Panel.objects.create(name="P2", base_url="https://ph", admin_username="a",
                                 admin_password_enc="p", is_active=True)
    plan = Plan.objects.create(name_fa="p", price=Decimal("1"), duration_days=30)
    svc = Service.objects.create(
        user=user, panel=panel, panel_username="hold-1", current_plan=plan,
        status=ServiceStatus.ON_HOLD, subscription_url="https://ph/s/tok/",
        data_limit=50 * 1024**3, data_used=0, on_hold_duration=30 * 86400,
        expire_at=None, online_at=None,
    )
    return user, svc


def test_onhold_service_shows_waiting_for_connection(onhold_setup):
    user, svc = onhold_setup
    c = APIClient(); c.force_authenticate(user)
    with responses.RequestsMock(assert_all_requests_are_fired=False) as r:
        r.add(responses.POST, "https://ph/api/admin/token", json={"access_token": "t"})
        r.add(responses.GET, "https://ph/api/user/hold-1",
              json={"username": "hold-1", "status": "on_hold", "used_traffic": 0,
                    "data_limit": 50 * 1024**3, "on_hold_expire_duration": 30 * 86400})
        row = c.get("/api/v1/services/").data["results"][0]
    assert row["status"] == "on_hold"
    assert row["waiting_for_connection"] is True
    assert row["validity_days"] == 30
    assert row["days_left"] is None


def test_first_connection_flips_status_to_active(onhold_setup):
    user, svc = onhold_setup
    c = APIClient(); c.force_authenticate(user)
    expire = (timezone.now() + timezone.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
    online = timezone.now().strftime("%Y-%m-%dT%H:%M:%S")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as r:
        r.add(responses.POST, "https://ph/api/admin/token", json={"access_token": "t"})
        r.add(responses.GET, "https://ph/api/user/hold-1",
              json={"username": "hold-1", "status": "active", "used_traffic": 2 * 1024**3,
                    "data_limit": 50 * 1024**3, "expire": expire, "online_at": online})
        row = c.get("/api/v1/services/").data["results"][0]
    assert row["status"] == "active"
    assert row["waiting_for_connection"] is False
    assert row["days_left"] in (29, 30)
    assert row["data_used"] == 2 * 1024**3
    svc.refresh_from_db()
    assert svc.status == "active" and svc.expire_at is not None


def test_refresh_action_forces_a_sync(onhold_setup):
    user, svc = onhold_setup
    c = APIClient(); c.force_authenticate(user)
    with responses.RequestsMock(assert_all_requests_are_fired=False) as r:
        r.add(responses.POST, "https://ph/api/admin/token", json={"access_token": "t"})
        r.add(responses.GET, "https://ph/api/user/hold-1",
              json={"username": "hold-1", "status": "active",
                    "expire": (timezone.now() + timezone.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S"),
                    "online_at": timezone.now().strftime("%Y-%m-%dT%H:%M:%S")})
        r2 = c.post(f"/api/v1/services/{svc.id}/refresh/")
    assert r2.status_code == 200
    assert r2.data["status"] == "active"
