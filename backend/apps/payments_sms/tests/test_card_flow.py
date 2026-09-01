import io
from decimal import Decimal

import pytest
import responses
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.orders.models import OrderStatus, OrderType
from apps.orders.services import create_order
from apps.panel.models import Panel, ServiceStatus
from apps.payments_sms.models import BankCard, Payment, PaymentStatus
from apps.payments_sms.services import approve_payment, reject_payment, submit_receipt
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db
BASE = "https://panel.test"


def _png():
    try:
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (4, 4)).save(buf, format="PNG")
        return SimpleUploadedFile("r.png", buf.getvalue(), content_type="image/png")
    except Exception:  # pragma: no cover
        return SimpleUploadedFile("r.png", b"\x89PNG\r\n", content_type="image/png")


@pytest.fixture
def user():
    return User.objects.create_user("cust", "Str0ngPass!")


@pytest.fixture
def panel():
    return Panel.objects.create(name="P", base_url=BASE, admin_username="a",
                                admin_password_enc="p", default_group_ids=[6])


@pytest.fixture
def plan():
    return Plan.objects.create(name_fa="30d", price=Decimal("100000"),
                               data_limit=50 * 1024**3, duration_days=30, group_ids=[6])


@pytest.fixture
def order(user, plan):
    return create_order(user=user, plan_id=plan.id, requested_account_name="cust-1")


def test_receipt_upload_creates_pending_payment(user, order):
    client = APIClient()
    client.force_authenticate(user)
    r = client.post("/api/v1/payments/receipt/",
                    {"order": order.id, "receipt_image": _png()}, format="multipart")
    assert r.status_code == 201, r.data
    assert r.data["status"] == PaymentStatus.PENDING
    assert Payment.objects.get(order=order).receipt_image


def test_receipt_upload_rejects_other_users_order(order):
    other = User.objects.create_user("mallory", "Str0ngPass!")
    client = APIClient()
    client.force_authenticate(other)
    r = client.post("/api/v1/payments/receipt/",
                    {"order": order.id, "receipt_image": _png()}, format="multipart")
    assert r.status_code == 400


@responses.activate
def test_approve_marks_paid_and_provisions(user, panel, plan, order, django_capture_on_commit_callbacks):
    responses.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"})
    responses.add(responses.POST, f"{BASE}/api/user", json={
        "username": "cust-1", "status": "on_hold", "subscription_url": f"{BASE}/myac/s/",
    }, status=200)

    submit_receipt(order=order, image=_png(), user=user)
    payment = Payment.objects.get(order=order)

    with django_capture_on_commit_callbacks(execute=True):
        approve_payment(payment.id)

    payment.refresh_from_db()
    order.refresh_from_db()
    assert payment.status == PaymentStatus.APPROVED
    assert payment.confirmed_by == "admin"
    assert order.status == OrderStatus.COMPLETED
    assert order.service is not None
    assert order.service.subscription_url == f"{BASE}/myac/s/"
    assert order.amount_unique_lock is None


def test_reject_keeps_order_open_for_retry(user, order):
    submit_receipt(order=order, image=_png(), user=user)
    payment = Payment.objects.get(order=order)
    reject_payment(payment.id, reason="blurry image")
    payment.refresh_from_db()
    order.refresh_from_db()
    assert payment.status == PaymentStatus.REJECTED
    assert payment.reject_reason == "blurry image"
    assert order.status == OrderStatus.PENDING_PAYMENT

    # customer can upload a fresh receipt -> back to pending
    submit_receipt(order=order, image=_png(), user=user)
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.PENDING


def test_approve_endpoint_is_admin_only(user, order):
    submit_receipt(order=order, image=_png(), user=user)
    payment = Payment.objects.get(order=order)
    client = APIClient()
    client.force_authenticate(user)
    assert client.post(f"/api/v1/payments/{payment.id}/approve/").status_code == 403


def test_cards_endpoint_lists_active(user):
    BankCard.objects.create(card_number="1", holder_name="A", is_active=True, sort_order=1)
    BankCard.objects.create(card_number="2", holder_name="B", is_active=False, sort_order=2)
    client = APIClient()
    client.force_authenticate(user)
    r = client.get("/api/v1/payments/cards/")
    assert r.status_code == 200
    assert len(r.data["results"]) == 1
