from decimal import Decimal

import pytest

from apps.accounts.models import User
from apps.panel.models import Panel, Service, ServiceStatus
from apps.plans.models import Plan, PlanType
from apps.telegram.shop import buy_new, plan_label, renew, service_summary

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return User.objects.create_user("u", "Str0ngPass!", telegram_id=9)


@pytest.fixture
def plan():
    return Plan.objects.create(name_fa="۳۰روزه", price=Decimal("120000"),
                               data_limit=50 * 1024**3, duration_days=30, group_ids=[6])


def test_buy_new_creates_bot_sourced_order(user, plan):
    order = buy_new(user, plan, account_name="tguser1")
    assert order.source == "bot"
    assert order.type == "new"
    assert order.amount == Decimal("120000")
    assert order.requested_account_name == "tguser1"


def test_renew_creates_renew_order(user, plan):
    panel = Panel.objects.create(name="P", base_url="https://x", admin_username="a", admin_password_enc="p")
    svc = Service.objects.create(user=user, panel=panel, panel_username="tguser1",
                                 current_plan=plan, status=ServiceStatus.EXPIRED)
    order = renew(user, svc, plan)
    assert order.type == "renew"
    assert order.service_id == svc.id
    assert order.source == "bot"


def test_plan_label_and_service_summary(user, plan):
    label = plan_label(plan)
    assert "۳۰روزه" in label and "50 گیگ" in label and "تومان" in label

    panel = Panel.objects.create(name="P", base_url="https://x", admin_username="a", admin_password_enc="p")
    svc = Service.objects.create(user=user, panel=panel, panel_username="x1", current_plan=plan,
                                 status=ServiceStatus.ACTIVE, data_limit=50 * 1024**3,
                                 data_used=10 * 1024**3)
    summary = service_summary(svc)
    assert "x1" in summary and "فعال" in summary and "10 از 50" in summary


def test_custom_volume_label(user):
    cv = Plan.objects.create(name_fa="حجمی", type=PlanType.CUSTOM_VOLUME, price=Decimal("0"),
                             price_per_gb=Decimal("2500"), min_gb=5, max_gb=100)
    assert "حجمی" in plan_label(cv)
