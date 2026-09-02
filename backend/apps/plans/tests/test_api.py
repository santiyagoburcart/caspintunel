from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.panel.models import Panel
from apps.plans.models import Plan, PlanType

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def panel():
    return Panel.objects.create(name="P", base_url="https://x", admin_username="a",
                                admin_password_enc="p")


def test_list_shows_only_active_plans_to_public(client):
    Plan.objects.create(name_fa="A", price=Decimal("100000"), is_active=True)
    Plan.objects.create(name_fa="B", price=Decimal("100000"), is_active=False)
    r = client.get("/api/v1/plans/")
    assert r.status_code == 200
    names = [p["name_fa"] for p in r.data["results"]]
    assert names == ["A"]


def test_admin_sees_inactive_and_can_create(client, panel):
    admin = User.objects.create_superuser("root", "Str0ngPass!")
    client.force_authenticate(admin)
    r = client.post("/api/v1/plans/", {
        "type": "fixed", "name_fa": "New", "price": 250000, "data_limit": 53687091200,
        "duration_days": 30, "group_ids": [6, 8], "panel": panel.id,
    }, format="json")
    assert r.status_code == 201, r.data
    plan = Plan.objects.get(name_fa="New")
    assert plan.group_ids == [6, 8]
    assert plan.panel_id == panel.id


def test_create_plan_requires_a_panel(client):
    admin = User.objects.create_superuser("root", "Str0ngPass!")
    client.force_authenticate(admin)
    r = client.post("/api/v1/plans/", {"type": "fixed", "name_fa": "NoPanel", "price": 1000},
                    format="json")
    assert r.status_code == 400
    assert "panel" in r.data


def test_custom_volume_plan_requires_price_per_gb(client):
    admin = User.objects.create_superuser("root", "Str0ngPass!")
    client.force_authenticate(admin)
    r = client.post("/api/v1/plans/", {"type": "custom_volume", "name_fa": "CV", "price": 0}, format="json")
    assert r.status_code == 400


def test_custom_volume_pricing_with_discount():
    plan = Plan.objects.create(
        name_fa="CV", type=PlanType.CUSTOM_VOLUME, price=Decimal("10000"),
        price_per_gb=Decimal("2000"), min_gb=5, max_gb=100, discount_percent=Decimal("10"),
    )
    # (10000 + 2000*20) * 0.9 = 45000
    assert plan.price_for_volume(20) == Decimal("45000")
    assert plan.data_limit_for_volume(20) == 20 * 1024**3
