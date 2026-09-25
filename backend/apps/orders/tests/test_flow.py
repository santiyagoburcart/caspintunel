from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.orders.models import Order, OrderStatus
from apps.orders.services import OrderError, create_order, expire_stale_reservations
from apps.panel.models import Panel
from apps.payments_sms.models import Payment, PaymentMethod, PaymentStatus
from apps.plans.models import Plan, PlanType
from apps.settings_app.utils import set_setting

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return User.objects.create_user("cust", "Str0ngPass!")


@pytest.fixture
def panel():
    return Panel.objects.create(name="P", base_url="https://x", admin_username="a",
                                admin_password_enc="p")


@pytest.fixture
def fixed_plan(panel):
    return Plan.objects.create(panel=panel, name_fa="30d", price=Decimal("100000"),
                               data_limit=50 * 1024**3, duration_days=30, discount_percent=Decimal("10"))


def test_create_fixed_order_allocates_unique_amount(user, fixed_plan):
    set_setting("unique_amount_min", "200", "int")
    set_setting("unique_amount_max", "1500", "int")
    order = create_order(user=user, plan_id=fixed_plan.id, requested_account_name="cust-1")
    assert order.amount == Decimal("90000")               # 10% discount
    assert Decimal("90200") <= order.amount_unique <= Decimal("91500")
    assert order.amount_unique_lock == order.amount_unique
    assert order.status == OrderStatus.PENDING_PAYMENT
    assert order.unique_expire_at > timezone.now()


def test_unique_amount_is_not_reused_while_active(user, fixed_plan):
    o1 = create_order(user=user, plan_id=fixed_plan.id, requested_account_name="a")
    o2 = create_order(user=user, plan_id=fixed_plan.id, requested_account_name="b")
    assert o1.amount_unique != o2.amount_unique


def test_fixed_new_order_needs_account_name(user, fixed_plan):
    with pytest.raises(OrderError):
        create_order(user=user, plan_id=fixed_plan.id)


def test_custom_volume_order_prices_by_gb(user, panel):
    plan = Plan.objects.create(panel=panel, name_fa="CV", type=PlanType.CUSTOM_VOLUME, price=Decimal("0"),
                               price_per_gb=Decimal("3000"), min_gb=5, max_gb=50)
    order = create_order(user=user, plan_id=plan.id, requested_account_name="cv-1", custom_volume_gb=10)
    assert order.amount == Decimal("30000")
    assert order.custom_volume_gb == 10


def test_custom_volume_out_of_range_rejected(user, panel):
    plan = Plan.objects.create(panel=panel, name_fa="CV", type=PlanType.CUSTOM_VOLUME, price=Decimal("0"),
                               price_per_gb=Decimal("3000"), min_gb=5, max_gb=50)
    with pytest.raises(OrderError):
        create_order(user=user, plan_id=plan.id, requested_account_name="cv-2", custom_volume_gb=100)


def test_expire_stale_reservations_releases_lock(user, fixed_plan):
    order = create_order(user=user, plan_id=fixed_plan.id, requested_account_name="x")
    Order.objects.filter(pk=order.id).update(unique_expire_at=timezone.now() - timezone.timedelta(minutes=1))

    assert expire_stale_reservations() == 1
    order.refresh_from_db()
    assert order.status == OrderStatus.EXPIRED
    assert order.amount_unique_lock is None


def test_reservation_not_expired_when_receipt_pending(user, fixed_plan):
    order = create_order(user=user, plan_id=fixed_plan.id, requested_account_name="y")
    Payment.objects.create(order=order, method=PaymentMethod.CARD_MANUAL,
                           amount=order.amount_unique, status=PaymentStatus.PENDING)
    Order.objects.filter(pk=order.id).update(unique_expire_at=timezone.now() - timezone.timedelta(minutes=1))
    assert expire_stale_reservations() == 0


def test_order_api_create_returns_payment_instructions(user, fixed_plan):
    from apps.payments_sms.models import BankCard
    BankCard.objects.create(card_number="6037-9911-1111-1111", holder_name="Owner", sort_order=1)

    client = APIClient()
    client.force_authenticate(user)
    r = client.post("/api/v1/orders/", {"plan": fixed_plan.id, "type": "new",
                                        "requested_account_name": "web-1",
                                        "terms_accepted": True}, format="json")
    assert r.status_code == 201, r.data
    pi = r.data["payment_instructions"]
    assert pi["amount_to_pay"] == r.data["order"]["amount_unique"]
    assert len(pi["cards"]) == 1
    assert "card_number" in pi["cards"][0]


def test_order_api_rejects_taken_account_name(user, fixed_plan):
    from apps.panel.models import Service
    Service.objects.create(user=user, panel=fixed_plan.panel, panel_username="taken", current_plan=fixed_plan)

    client = APIClient()
    client.force_authenticate(user)
    r = client.post("/api/v1/orders/", {"plan": fixed_plan.id, "requested_account_name": "taken",
                                        "terms_accepted": True}, format="json")
    assert r.status_code == 400


def test_order_no_longer_asks_for_terms(user, fixed_plan):
    """Terms are accepted once, at sign-up — checkout doesn't ask again."""
    client = APIClient()
    client.force_authenticate(user)
    r = client.post("/api/v1/orders/", {"plan": fixed_plan.id, "requested_account_name": "no-terms"}, format="json")
    assert r.status_code == 201, r.data


def test_new_order_rejects_a_taken_account_name(user, fixed_plan):
    from apps.panel.models import Service
    other = User.objects.create_user("other", "Str0ngPass!")
    Service.objects.create(user=other, panel=fixed_plan.panel, panel_username="taken", current_plan=fixed_plan)
    with pytest.raises(OrderError):
        create_order(user=user, plan_id=fixed_plan.id, requested_account_name="taken")


def test_new_order_allows_same_name_on_a_different_panel(user, fixed_plan):
    """multi-panel: username uniqueness is per-panel."""
    from apps.panel.models import Panel, Service
    other_panel = Panel.objects.create(name="P2", base_url="https://y", admin_username="a",
                                       admin_password_enc="p")
    Service.objects.create(user=user, panel=other_panel, panel_username="shared", current_plan=fixed_plan)
    # fixed_plan is on a different panel -> the name is free there
    order = create_order(user=user, plan_id=fixed_plan.id, requested_account_name="shared")
    assert order.requested_account_name == "shared"


def test_custom_volume_new_order_requires_account_name(user, panel):
    """The customer must pick their own username for custom-volume plans too —
    we never auto-generate it."""
    from apps.plans.models import PlanType
    plan = Plan.objects.create(panel=panel, name_fa="CV2", type=PlanType.CUSTOM_VOLUME, price=Decimal("0"),
                               price_per_gb=Decimal("1000"), min_gb=1, max_gb=100)
    with pytest.raises(OrderError):
        create_order(user=user, plan_id=plan.id, custom_volume_gb=10)  # no account name

    order = create_order(user=user, plan_id=plan.id, custom_volume_gb=10,
                         requested_account_name="myvpn")
    assert order.requested_account_name == "myvpn"
