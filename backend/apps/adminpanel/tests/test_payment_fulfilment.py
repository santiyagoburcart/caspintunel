"""Rejected orders are closed (never resumed, shown as rejected) and ANY move
of a payment into `approved` — incl. rejected -> approved from the admin
transaction page — runs the real fulfilment exactly once."""
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import User
from apps.notifications.models import Notification
from apps.orders.models import Order, OrderStatus
from apps.orders.serializers import OrderSerializer
from apps.orders.services import create_order
from apps.payments_sms.models import Payment, PaymentMethod, PaymentStatus
from apps.payments_sms.services import PaymentError, approve_payment, reject_payment
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db(transaction=True)

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4"
       b"\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82")


@pytest.fixture
def fulfil_calls(monkeypatch):
    calls = []
    from apps.orders import tasks

    monkeypatch.setattr(tasks.fulfill_order, "delay", lambda order_id: calls.append(order_id))
    return calls


@pytest.fixture
def plan50():
    return Plan.objects.create(name_fa="بسته 50 گیگ", price=Decimal("250000"), data_limit=50 * 1024**3,
                               duration_days=30, group_ids=[1])


@pytest.fixture
def cust():
    return User.objects.create_user("buyer", "Str0ngPass!")


def _order_with_receipt(user, plan, name="acc-1", source="site"):
    order = create_order(user=user, plan_id=plan.id, requested_account_name=name, source=source)
    pay = Payment.objects.create(order=order, method=PaymentMethod.CARD_MANUAL, amount=order.amount_unique,
                                 status=PaymentStatus.PENDING,
                                 receipt_image=SimpleUploadedFile("r.png", PNG, content_type="image/png"))
    return order, pay


# --- 1) rejected orders -------------------------------------------------
def test_reject_closes_the_order_and_shows_rejected_with_reason(cust, plan50, fulfil_calls):
    order, pay = _order_with_receipt(cust, plan50)
    reject_payment(pay.id, reason="مبلغ مطابقت ندارد")
    order.refresh_from_db()
    assert order.status == OrderStatus.REJECTED
    assert order.amount_unique_lock is None                      # unique amount released
    data = OrderSerializer(order).data
    assert data["status"] == "rejected" and data["payment_status"] == "rejected"
    assert data["reject_reason"] == "مبلغ مطابقت ندارد"
    assert Notification.objects.filter(target_user=cust, title__contains="رد شد").exists()
    assert fulfil_calls == []


@pytest.mark.parametrize("source", ["site", "bot"])
def test_buying_again_after_rejection_creates_a_new_order(cust, plan50, fulfil_calls, source):
    order, pay = _order_with_receipt(cust, plan50, source=source)
    reject_payment(pay.id, reason="x")
    again = create_order(user=cust, plan_id=plan50.id, requested_account_name="acc-1", source=source)
    assert again.id != order.id and again.reused is False
    assert again.amount_unique != order.amount_unique            # never the old amount
    assert again.status == OrderStatus.PENDING_PAYMENT


def test_pending_order_with_a_rejected_payment_is_never_reused(cust, plan50):
    """Legacy rows (rejected before this fix kept the order pending_payment)."""
    order, pay = _order_with_receipt(cust, plan50)
    Payment.objects.filter(pk=pay.pk).update(status=PaymentStatus.REJECTED, reject_reason="old")
    again = create_order(user=cust, plan_id=plan50.id, requested_account_name="acc-1")
    assert again.id != order.id


def test_open_pending_order_is_still_resumed(cust, plan50):
    order = create_order(user=cust, plan_id=plan50.id, requested_account_name="acc-1")
    again = create_order(user=cust, plan_id=plan50.id, requested_account_name="acc-1")
    assert again.id == order.id and again.reused is True


@pytest.mark.parametrize("status", [OrderStatus.EXPIRED, OrderStatus.COMPLETED, OrderStatus.REJECTED])
def test_closed_orders_are_never_reused(cust, plan50, status):
    order = create_order(user=cust, plan_id=plan50.id, requested_account_name="acc-1")
    Order.objects.filter(pk=order.pk).update(status=status)
    again = create_order(user=cust, plan_id=plan50.id, requested_account_name="acc-1")
    assert again.id != order.id


# --- 2) any transition into approved fulfils ---------------------------------
def test_rejected_to_approved_from_the_transaction_page_fulfils(cust, plan50, fulfil_calls, staff_client, superadmin):
    order, pay = _order_with_receipt(cust, plan50)
    reject_payment(pay.id, reason="اشتباه")
    r = staff_client(superadmin).post(f"/api/v1/admin/transactions/{pay.id}/status/", {"status": "approved"}, format="json")
    assert r.status_code == 200, r.content
    pay.refresh_from_db(); order.refresh_from_db()
    assert pay.status == PaymentStatus.APPROVED and pay.reject_reason == ""
    assert pay.confirmed_by == "admin" and pay.confirmed_by_staff_id == superadmin.id
    assert order.status == OrderStatus.PAID
    assert fulfil_calls == [order.id]
    assert Notification.objects.filter(target_user=cust, title__contains="تأیید").exists()
    # idempotent: approving again never provisions twice
    staff_client(superadmin).post(f"/api/v1/admin/transactions/{pay.id}/status/", {"status": "approved"}, format="json")
    approve_payment(pay.id)
    assert fulfil_calls == [order.id]


def test_pending_to_approved_still_fulfils(cust, plan50, fulfil_calls):
    order, pay = _order_with_receipt(cust, plan50)
    approve_payment(pay.id)
    order.refresh_from_db()
    assert order.status == OrderStatus.PAID and fulfil_calls == [order.id]


def test_approving_when_the_order_is_already_completed_does_not_reprovision(cust, plan50, fulfil_calls):
    order, pay = _order_with_receipt(cust, plan50)
    Order.objects.filter(pk=order.pk).update(status=OrderStatus.COMPLETED)
    Payment.objects.filter(pk=pay.pk).update(status=PaymentStatus.REJECTED)
    approve_payment(pay.id)
    assert fulfil_calls == []


def test_late_approval_when_the_amount_was_taken_meanwhile(cust, plan50, fulfil_calls):
    """The rejected order released its unique amount; another customer's open
    order got it. Approving the old one must still pay + fulfil it."""
    order, pay = _order_with_receipt(cust, plan50)
    reject_payment(pay.id, reason="x")
    other = User.objects.create_user("other", "Str0ngPass!")
    o2 = create_order(user=other, plan_id=plan50.id, requested_account_name="acc-2")
    Order.objects.filter(pk=o2.pk).update(amount_unique=order.amount_unique, amount_unique_lock=order.amount_unique)
    approve_payment(pay.id)
    order.refresh_from_db()
    assert order.status == OrderStatus.PAID and order.amount_unique_lock is None
    assert fulfil_calls == [order.id]


def test_cannot_reject_a_paid_order(cust, plan50, fulfil_calls):
    order, pay = _order_with_receipt(cust, plan50)
    Order.objects.filter(pk=order.pk).update(status=OrderStatus.PAID)
    with pytest.raises(PaymentError):
        reject_payment(pay.id, reason="x")
