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


def test_receipt_links_to_sole_active_card_for_deposit_report(user, order):
    """Bug fix: card-to-card payments used to save bank_card=NULL, so the
    per-card deposit total (BankCard.deposit_total) stayed 0 forever."""
    card = BankCard.objects.create(card_number="6037-XXXX", holder_name="H", is_active=True)
    submit_receipt(order=order, image=_png(), user=user)
    payment = Payment.objects.get(order=order)
    assert payment.bank_card_id == card.id  # auto-linked at upload time

    approve_payment(payment.id)
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.APPROVED
    assert payment.bank_card_id == card.id


def test_admin_can_set_deposit_card_at_approval(user, order):
    c1 = BankCard.objects.create(card_number="AAAA", holder_name="A", is_active=True, sort_order=1)
    c2 = BankCard.objects.create(card_number="BBBB", holder_name="B", is_active=True, sort_order=2)
    submit_receipt(order=order, image=_png(), user=user)
    payment = Payment.objects.get(order=order)
    assert payment.bank_card_id is None  # ambiguous: two active cards

    approve_payment(payment.id, bank_card=c2)
    payment.refresh_from_db()
    assert payment.bank_card_id == c2.id
    assert c1.payments.count() == 0


def test_cards_endpoint_lists_active(user):
    BankCard.objects.create(card_number="1", holder_name="A", is_active=True, sort_order=1)
    BankCard.objects.create(card_number="2", holder_name="B", is_active=False, sort_order=2)
    client = APIClient()
    client.force_authenticate(user)
    r = client.get("/api/v1/payments/cards/")
    assert r.status_code == 200
    assert len(r.data["results"]) == 1


# --- receipt file access control (ReceiptFileView) -----------------------
def _pending_payment(user, order):
    from apps.payments_sms.services import submit_receipt
    submit_receipt(order=order, image=_png(), user=user)
    return Payment.objects.get(order=order)


def test_receipt_file_served_to_owner(user, order):
    p = _pending_payment(user, order)
    c = APIClient(); c.force_authenticate(user)
    r = c.get(f"/api/v1/payments/{p.id}/receipt/")
    assert r.status_code == 200
    assert r["Content-Type"].startswith("image/")


def test_receipt_file_hidden_from_other_users(user, order):
    p = _pending_payment(user, order)
    mallory = User.objects.create_user("mallory2", "Str0ngPass!")
    c = APIClient(); c.force_authenticate(mallory)
    assert c.get(f"/api/v1/payments/{p.id}/receipt/").status_code == 404


def test_receipt_file_requires_auth(user, order):
    p = _pending_payment(user, order)
    assert APIClient().get(f"/api/v1/payments/{p.id}/receipt/").status_code in (401, 403)


def test_receipt_file_served_to_staff(user, order, django_user_model):
    p = _pending_payment(user, order)
    staff = django_user_model.objects.create_user("op", "Str0ngPass!", is_staff=True)
    c = APIClient(); c.force_authenticate(staff)
    assert c.get(f"/api/v1/payments/{p.id}/receipt/").status_code == 200


def test_receipt_file_served_to_panel_operator_with_perm(user, order):
    from apps.accounts.models import Permission, Role, Staff
    from apps.adminpanel.tokens import issue_tokens
    p = _pending_payment(user, order)
    role = Role.objects.create(name="ops")
    role.permissions.add(Permission.objects.create(code="payment.view", name="v"))
    op = Staff(username="viewer", role=role); op.set_password("x"); op.save()
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(op)['access']}")
    assert c.get(f"/api/v1/payments/{p.id}/receipt/").status_code == 200

    noperm = Staff(username="noperm", role=Role.objects.create(name="empty"))
    noperm.set_password("x"); noperm.save()
    c2 = APIClient()
    c2.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(noperm)['access']}")
    assert c2.get(f"/api/v1/payments/{p.id}/receipt/").status_code == 404


def test_receipt_url_is_not_a_public_media_path(user, order):
    p = _pending_payment(user, order)
    c = APIClient(); c.force_authenticate(user)
    from apps.payments_sms.serializers import PaymentSerializer
    data = PaymentSerializer(p).data
    assert data["receipt_url"] == f"/api/v1/payments/{p.id}/receipt/"
    assert "receipt_image" not in data
