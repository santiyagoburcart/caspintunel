from decimal import Decimal

import pytest
import responses
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.orders.models import OrderStatus
from apps.orders.services import create_order
from apps.panel.models import Panel
from apps.payments_sms.models import (
    ConfirmedBy,
    Payment,
    PaymentMethod,
    PaymentStatus,
    SmsAppDevice,
    SmsMessage,
    SmsSource,
)
from apps.payments_sms.parsing import candidate_amounts, extract_numbers
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db
BASE = "https://panel.test"


# --- parsing ----------------------------------------------------------
def test_persian_digits_and_separators():
    assert extract_numbers("مبلغ ۱۵۰٬۰۰۰ تومان") == [150000]
    assert extract_numbers("deposit 1,502,300 RIAL") == [1502300]


def test_rial_to_toman_candidates():
    cands = candidate_amounts("واریز 1,512,590 ریال")
    assert Decimal("1512590") in cands
    assert Decimal("151259") in cands   # /10


# --- fixtures -------------------------------------------------------
@pytest.fixture
def device():
    return SmsAppDevice.objects.create(name="pixel", is_active=True)


@pytest.fixture
def panel():
    return Panel.objects.create(name="P", base_url=BASE, admin_username="a",
                                admin_password_enc="p", default_group_ids=[6])


@pytest.fixture
def order():
    user = User.objects.create_user("cust", "Str0ngPass!")
    plan = Plan.objects.create(name_fa="p", price=Decimal("100000"), data_limit=1024**3,
                               duration_days=30, group_ids=[6])
    return create_order(user=user, plan_id=plan.id, requested_account_name="cust-1")


def _client(token=None):
    c = APIClient()
    if token:
        c.credentials(HTTP_X_DEVICE_TOKEN=token)
    return c


# --- auth --------------------------------------------------------
def test_inbound_requires_valid_device_token():
    assert _client().post("/api/v1/payments/sms/inbound/", {"text": "x"}, format="json").status_code == 401
    assert _client("nope").post("/api/v1/payments/sms/inbound/", {"text": "x"}, format="json").status_code == 401


def test_ping_updates_last_seen(device):
    assert device.last_seen_at is None
    r = _client(device.api_token).get("/api/v1/payments/sms/ping/")
    assert r.status_code == 200 and r.data["device"] == "pixel"
    device.refresh_from_db()
    assert device.last_seen_at is not None


# --- matching (flowchart 1.4) --------------------------------------
@responses.activate
def test_matching_amount_auto_confirms_and_provisions(device, panel, order, django_capture_on_commit_callbacks):
    responses.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"})
    responses.add(responses.POST, f"{BASE}/api/user",
                  json={"username": "cust-1", "status": "on_hold", "subscription_url": f"{BASE}/myac/s/"},
                  status=200)

    rial = int(order.amount_unique * 10)   # bank quotes rials
    text = f"مبلغ {rial:,} ریال به حساب شما واریز شد"

    with django_capture_on_commit_callbacks(execute=True):
        r = _client(device.api_token).post(
            "/api/v1/payments/sms/inbound/", {"text": text, "sender": "+985000"}, format="json"
        )
    assert r.status_code == 201, r.data
    assert r.data["matched"] is True and r.data["order_id"] == order.id

    payment = Payment.objects.get(order=order)
    assert payment.method == PaymentMethod.SMS_AUTO
    assert payment.status == PaymentStatus.APPROVED
    assert payment.confirmed_by == ConfirmedBy.SYSTEM
    order.refresh_from_db()
    assert order.status == OrderStatus.COMPLETED
    assert SmsMessage.objects.get(pk=payment.sms_message_id).matched_order_id == order.id


def test_no_matching_order_is_stored_unmatched(device, order):
    r = _client(device.api_token).post(
        "/api/v1/payments/sms/inbound/", {"text": "مبلغ 999999 تومان"}, format="json"
    )
    assert r.status_code == 201
    assert r.data["matched"] is False
    assert SmsMessage.objects.count() == 1
    assert Payment.objects.count() == 0


def test_second_identical_sms_does_not_double_confirm(device, panel, order, django_capture_on_commit_callbacks):
    with responses.RequestsMock() as rsps:
        rsps.add(rsps.POST, f"{BASE}/api/admin/token", json={"access_token": "t"})
        rsps.add(rsps.POST, f"{BASE}/api/user",
                 json={"username": "cust-1", "status": "on_hold", "subscription_url": f"{BASE}/x/"})
        text = f"واریز {int(order.amount_unique)} تومان"
        with django_capture_on_commit_callbacks(execute=True):
            _client(device.api_token).post("/api/v1/payments/sms/inbound/", {"text": text}, format="json")

    r2 = _client(device.api_token).post("/api/v1/payments/sms/inbound/", {"text": text}, format="json")
    assert r2.data["matched"] is False
    assert Payment.objects.filter(order=order).count() == 1


# --- sender allow-list -------------------------------------------
def test_sender_not_in_allowlist_is_not_confirmed(device, order):
    SmsSource.objects.create(phone_number="98200028", description="Bank", is_active=True)
    text = f"واریز {int(order.amount_unique)} تومان"
    r = _client(device.api_token).post(
        "/api/v1/payments/sms/inbound/", {"text": text, "sender": "+9899999"}, format="json"
    )
    assert r.data["matched"] is False
    assert "allowed" in r.data["reason"]
    assert Payment.objects.count() == 0


@responses.activate
def test_allowed_sender_matches(device, panel, order, django_capture_on_commit_callbacks):
    responses.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"})
    responses.add(responses.POST, f"{BASE}/api/user",
                  json={"username": "cust-1", "status": "on_hold", "subscription_url": f"{BASE}/x/"})
    SmsSource.objects.create(phone_number="200028", is_active=True)
    text = f"واریز {int(order.amount_unique)} تومان از 200028"
    with django_capture_on_commit_callbacks(execute=True):
        r = _client(device.api_token).post(
            "/api/v1/payments/sms/inbound/", {"text": text, "sender": "50002 0002 8"}, format="json"
        )
    assert r.data["matched"] is True
