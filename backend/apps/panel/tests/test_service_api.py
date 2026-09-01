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
