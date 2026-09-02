"""Admin card-to-card approval queue: /admin/payments/pending + approve/reject."""
import io
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import User
from apps.adminpanel.tests.conftest import make_staff
from apps.orders.models import Order, OrderStatus, OrderType
from apps.orders.services import create_order
from apps.payments_sms.services import submit_receipt
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db


def _png():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (4, 4)).save(buf, format="PNG")
    return SimpleUploadedFile("r.png", buf.getvalue(), content_type="image/png")


@pytest.fixture
def plan():
    return Plan.objects.create(name_fa="P", price=Decimal("100000"),
                               data_limit=10 * 1024**3, duration_days=30)


@pytest.fixture
def pending_payment(plan):
    u = User.objects.create_user("cust", "Str0ngPass!")
    order = create_order(user=u, plan_id=plan.id, requested_account_name="acc-1")
    return submit_receipt(order=order, image=_png(), user=u)


@pytest.fixture
def boss(staff_client, superadmin):
    return staff_client(superadmin)


def test_pending_queue_lists_receipts_from_site_and_bot(boss, plan):
    site_u = User.objects.create_user("s", "x")
    bot_u = User.objects.create_user("b", "x", telegram_id=1)
    o1 = create_order(user=site_u, plan_id=plan.id, requested_account_name="s1")
    o2 = create_order(user=bot_u, plan_id=plan.id, order_type=OrderType.NEW,
                      requested_account_name="b1", source="bot")
    submit_receipt(order=o1, image=_png(), user=site_u)
    submit_receipt(order=o2, image=_png(), user=bot_u)

    r = boss.get("/api/v1/admin/payments/pending/")
    assert r.status_code == 200
    assert r.data["count"] == 2
    sources = {row["order_source"] for row in r.data["results"]}
    assert sources == {"site", "bot"}
    assert all(row["receipt_url"].startswith("/api/v1/payments/") for row in r.data["results"])
    assert all(row["status"] == "pending" for row in r.data["results"])


def test_approve_from_queue_marks_paid(boss, pending_payment):
    # (fulfilment runs on transaction.on_commit -> not executed here; the money
    #  decision itself must still land)
    r = boss.post(f"/api/v1/admin/payments/{pending_payment.id}/approve/")
    assert r.status_code == 200
    pending_payment.refresh_from_db()
    assert pending_payment.status == "approved"
    assert pending_payment.confirmed_by == "admin"
    pending_payment.order.refresh_from_db()
    assert pending_payment.order.status == OrderStatus.PAID
    # falls off the queue
    assert boss.get("/api/v1/admin/payments/pending/").data["count"] == 0


def test_reject_from_queue_keeps_order_open(boss, pending_payment):
    r = boss.post(f"/api/v1/admin/payments/{pending_payment.id}/reject/", {"reason": "blurry"}, format="json")
    assert r.status_code == 200
    pending_payment.refresh_from_db()
    assert pending_payment.status == "rejected"
    assert pending_payment.reject_reason == "blurry"
    pending_payment.order.refresh_from_db()
    assert pending_payment.order.status == OrderStatus.PENDING_PAYMENT


def test_queue_needs_payment_view_perm(staff_client, perms, pending_payment):
    weak = staff_client(make_staff("weak", ["monitoring.view"], perms))
    assert weak.get("/api/v1/admin/payments/pending/").status_code == 403
    viewer = staff_client(make_staff("viewer", ["payment.view"], perms))
    assert viewer.get("/api/v1/admin/payments/pending/").status_code == 200


def test_decision_needs_payment_approve_perm(staff_client, perms, pending_payment):
    viewer = staff_client(make_staff("viewer2", ["payment.view"], perms))
    assert viewer.post(f"/api/v1/admin/payments/{pending_payment.id}/approve/").status_code == 403
    approver = staff_client(make_staff("appr", ["payment.approve"], perms))
    # (approve makes a panel call; just assert the perm gate passed, not 403)
    assert approver.post(f"/api/v1/admin/payments/{pending_payment.id}/reject/",
                         {"reason": "x"}, format="json").status_code == 200
