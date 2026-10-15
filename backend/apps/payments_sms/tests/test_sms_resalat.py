"""SMS amount parsing for real bank formats (Bank Resalat, Blu), the reasons
stored on every SMS, the empty-text inbound that used to vanish, and the
admin SMS log."""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Staff, User
from apps.adminpanel.tokens import issue_tokens
from apps.orders.models import Order, OrderStatus
from apps.orders.services import create_order
from apps.payments_sms.matching import ingest_sms, mask_sms
from apps.payments_sms.models import SmsAppDevice, SmsMessage, SmsSource
from apps.payments_sms.parsing import deposit_amount, deposit_amounts
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db

RESALAT = "بانک رسالت\nواريز به حساب: 10.1234567.1\nمبلغ: ۲,۵۰۴,۳۰۰ ريال\nتاريخ: 1405/07/18 18:05\nمانده: 12,345,678 ريال"
RESALAT_PLUS = "رسالت\n+2,504,300\n10.123456.1\n0718-1805\nمانده:12,345,678"
RESALAT_LINE = "رسالت: واريز 2504300 ريال به حساب 10.1234567.1 مانده 12345678"
RESALAT_CARD = "بانک رسالت\nانتقال به کارت 5041-72**-****-1234\nمبلغ 2,504,300 ریال\n18:05"
BLU_DEPOSIT = "بلو\nواریز پول\nپویا عزیز، 2,500,000ریال به حساب شما نشست.\nموجودی: 9,876,543 ریال"
BLU_WITHDRAW = "بلو\nبرداشت پول\nپویا عزیز، 3,000,000 ریال از حساب شما برداشت شد."
RESALAT_WITHDRAW = "رسالت\n-1,000,000\n10.123456.1\nمانده:5,000,000"


@pytest.mark.parametrize("text", [RESALAT, RESALAT_PLUS, RESALAT_LINE, RESALAT_CARD])
def test_resalat_formats_give_the_deposit_amount_only(text):
    assert deposit_amounts(text) == [2504300]
    a = deposit_amount(text)                          # RESALAT_PLUS names no unit -> source default (rial)
    assert a.toman == Decimal("250430") and a.raw == 2504300


def test_rial_text_reports_tomans_in_the_log():
    assert deposit_amount(RESALAT).toman == Decimal("250430")
    assert deposit_amount(BLU_DEPOSIT).toman == Decimal("250000")


@pytest.mark.parametrize("text", [BLU_WITHDRAW, RESALAT_WITHDRAW])
def test_withdrawals_yield_nothing(text):
    assert deposit_amounts(text) == [] and deposit_amount(text) is None


def test_blu_deposit_on_the_next_line():
    assert deposit_amounts(BLU_DEPOSIT) == [2500000]


def test_card_numbers_dates_and_persian_digits():
    assert deposit_amounts("واریز ۲۵۰٬۴۳۰ تومان به کارت ۶۰۳۷-۹۹۱۲-۳۴۵۶-۷۸۹۰ در 1405/07/18") == [250430]


# --- ingest: notes, sender names -------------------------------------
@pytest.fixture
def device():
    return SmsAppDevice.objects.create(name="iPhone", is_active=True)


@pytest.fixture
def order(monkeypatch):
    from apps.orders import tasks

    monkeypatch.setattr(tasks.fulfill_order, "delay", lambda *_: None)
    user = User.objects.create_user("cust", "Str0ngPass!")
    plan = Plan.objects.create(name_fa="p", price=Decimal("250000"), data_limit=1024**3, duration_days=30)
    o = create_order(user=user, plan_id=plan.id, requested_account_name="c1")
    Order.objects.filter(pk=o.pk).update(amount_unique=Decimal("250430"), amount_unique_lock=Decimal("250430"))
    o.refresh_from_db()
    return o


@pytest.mark.django_db(transaction=True)
def test_resalat_sms_auto_confirms_with_a_named_sender(device, order):
    SmsSource.objects.create(phone_number="Resalat", description="Bank Resalat")
    msg, res = ingest_sms(device=device, raw_text=RESALAT, sender="RESALAT")
    assert res["matched"] is True and res["order_id"] == order.id
    msg.refresh_from_db()
    assert msg.sender == "RESALAT" and "matched order" in msg.note


def test_unmatched_sms_says_why(device, order):
    Order.objects.filter(pk=order.pk).update(status=OrderStatus.EXPIRED, amount_unique_lock=None)
    msg, res = ingest_sms(device=device, raw_text=RESALAT, sender="")
    msg.refresh_from_db()
    assert res["matched"] is False and msg.parsed_amount == Decimal("250430")
    assert f"order #{order.id}" in msg.note and "expired" in msg.note


def test_sender_not_allowed_is_explained(device, order):
    SmsSource.objects.create(phone_number="+989999987641")
    msg, _ = ingest_sms(device=device, raw_text=RESALAT, sender="Resalat")
    msg.refresh_from_db()
    assert "not in Settings" in msg.note and msg.matched_order_id is None


def test_empty_text_from_the_iphone_is_logged_not_lost(device):
    c = APIClient()
    c.credentials(HTTP_X_DEVICE_TOKEN=device.api_token)
    r = c.post("/api/v1/payments/sms/inbound/", {"text": "", "sender": "Resalat"}, format="json")
    assert r.status_code == 400 and list(r.json()) == ["text"]   # "may not be blank"
    m = SmsMessage.objects.get()
    assert m.device_id == device.id and m.sender == "Resalat"
    assert "empty message body" in m.note


# --- admin SMS log ------------------------------------------------------
def test_mask_keeps_amounts_hides_card_and_account_digits():
    out = mask_sms("کارت 6037-9912-3456-7890 حساب 10.1234567.1 مبلغ 2,504,300 ریال")
    assert "6037" not in out and "7890" in out and "1234567" not in out and "2,504,300" in out


def test_admin_sms_log_lists_masked_text_and_reason(device, order):
    ingest_sms(device=device, raw_text="واریز 2,504,300 ریال به کارت 6037-9912-3456-7890", sender="Resalat")
    boss = Staff(username="boss", is_superadmin=True); boss.set_password("x-Str0ng!"); boss.save()
    c = APIClient(); c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(boss)['access']}")
    rows = c.get("/api/v1/admin/sms-log/").json()["results"]
    assert len(rows) == 1 and rows[0]["sender"] == "Resalat" and "6037-9912" not in rows[0]["text"]
    assert rows[0]["matched_order"] == order.id and rows[0]["note"]
    assert len(c.get("/api/v1/admin/sms-log/?matched=0").json()["results"]) == 0


def test_admin_sms_log_needs_payment_view(device):
    nobody = Staff(username="n"); nobody.set_password("x-Str0ng!"); nobody.save()
    c = APIClient(); c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(nobody)['access']}")
    assert c.get("/api/v1/admin/sms-log/").status_code == 403
