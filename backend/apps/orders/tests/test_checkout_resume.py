"""Checkout resume: re-submitting the same purchase while its unique-amount
reservation is still active must hand back the SAME order (and amount), and
the invoice must be restorable by id after a reload."""
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.orders.models import Order, OrderStatus
from apps.orders.services import create_order
from apps.payments_sms.models import BankCard
from apps.plans.models import Plan, PlanType

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return User.objects.create_user("cust", "Str0ngPass!")


@pytest.fixture
def plan():
    return Plan.objects.create(name_fa="30d", price=Decimal("100000"), data_limit=50 * 1024**3, duration_days=30)


@pytest.fixture
def client(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def test_same_purchase_reuses_pending_order(user, plan):
    o1 = create_order(user=user, plan_id=plan.id, requested_account_name="Ali")
    o2 = create_order(user=user, plan_id=plan.id, requested_account_name="ali")  # case-insensitive
    assert o2.id == o1.id
    assert o2.amount_unique == o1.amount_unique
    assert o2.reused is True and o1.reused is False
    assert Order.objects.count() == 1


def test_different_account_name_gets_new_order(user, plan):
    o1 = create_order(user=user, plan_id=plan.id, requested_account_name="a1")
    o2 = create_order(user=user, plan_id=plan.id, requested_account_name="a2")
    assert o1.id != o2.id


def test_other_user_never_gets_someone_elses_order(user, plan):
    other = User.objects.create_user("other", "Str0ngPass!")
    o1 = create_order(user=user, plan_id=plan.id, requested_account_name="same")
    o2 = create_order(user=other, plan_id=plan.id, requested_account_name="same")
    assert o1.id != o2.id


def test_expired_reservation_is_not_reused(user, plan):
    o1 = create_order(user=user, plan_id=plan.id, requested_account_name="x")
    Order.objects.filter(pk=o1.id).update(unique_expire_at=timezone.now() - timezone.timedelta(seconds=1))
    o2 = create_order(user=user, plan_id=plan.id, requested_account_name="x")
    assert o2.id != o1.id


def test_paid_order_is_not_reused(user, plan):
    o1 = create_order(user=user, plan_id=plan.id, requested_account_name="x")
    Order.objects.filter(pk=o1.id).update(status=OrderStatus.PAID)
    o2 = create_order(user=user, plan_id=plan.id, requested_account_name="x")
    assert o2.id != o1.id


def test_custom_volume_must_match_to_reuse(user):
    cv = Plan.objects.create(name_fa="CV", type=PlanType.CUSTOM_VOLUME, price=Decimal("0"),
                             price_per_gb=Decimal("3000"), min_gb=5, max_gb=50)
    o1 = create_order(user=user, plan_id=cv.id, requested_account_name="cv", custom_volume_gb=10)
    o2 = create_order(user=user, plan_id=cv.id, requested_account_name="cv", custom_volume_gb=10)
    o3 = create_order(user=user, plan_id=cv.id, requested_account_name="cv", custom_volume_gb=20)
    assert o1.id == o2.id and o3.id != o1.id


def test_api_resubmit_returns_same_invoice(client, plan):
    BankCard.objects.create(card_number="6037991234567890", holder_name="H", is_active=True)
    body = {"plan": plan.id, "type": "new", "requested_account_name": "acc1", "terms_accepted": True}
    r1 = client.post("/api/v1/orders/", body, format="json")
    assert r1.status_code == 201 and r1.data["reused"] is False
    r2 = client.post("/api/v1/orders/", body, format="json")
    assert r2.status_code == 200 and r2.data["reused"] is True
    assert r2.data["order"]["id"] == r1.data["order"]["id"]
    assert r2.data["payment_instructions"]["amount_to_pay"] == r1.data["payment_instructions"]["amount_to_pay"]


def test_checkout_endpoint_restores_invoice(client, user, plan):
    BankCard.objects.create(card_number="6037991234567890", holder_name="H", is_active=True)
    order = create_order(user=user, plan_id=plan.id, requested_account_name="acc2")
    r = client.get(f"/api/v1/orders/{order.id}/checkout/")
    assert r.status_code == 200
    assert r.data["order"]["id"] == order.id
    assert Decimal(r.data["payment_instructions"]["amount_to_pay"]) == order.amount_unique
    assert len(r.data["payment_instructions"]["cards"]) == 1


def test_checkout_endpoint_is_owner_only(plan):
    owner = User.objects.create_user("own", "Str0ngPass!")
    order = create_order(user=owner, plan_id=plan.id, requested_account_name="acc3")
    intruder = APIClient()
    intruder.force_authenticate(User.objects.create_user("bad", "Str0ngPass!"))
    assert intruder.get(f"/api/v1/orders/{order.id}/checkout/").status_code == 404
