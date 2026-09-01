from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.accounts.models import User
from apps.orders.models import Order, OrderStatus
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db


def _order(user, plan, amount_unique, status=OrderStatus.PENDING_PAYMENT):
    o = Order(
        user=user, plan=plan, amount=Decimal("100000"),
        amount_unique=Decimal(amount_unique), status=status,
        unique_expire_at=timezone.now() + timedelta(minutes=30),
    )
    o.sync_unique_lock()
    o.save()
    return o


def test_active_unique_amount_is_globally_unique():
    u = User.objects.create_user("u", "pw12345!")
    p = Plan.objects.create(name_fa="P", price=Decimal("100000"))
    _order(u, p, "100500")
    with pytest.raises(IntegrityError):
        _order(u, p, "100500")


def test_completed_order_releases_the_lock():
    u = User.objects.create_user("u", "pw12345!")
    p = Plan.objects.create(name_fa="P", price=Decimal("100000"))
    o1 = _order(u, p, "100700")
    o1.status = OrderStatus.COMPLETED
    o1.sync_unique_lock()
    o1.save()
    assert o1.amount_unique_lock is None
    # the same surcharged amount can now be reused
    _order(u, p, "100700")
