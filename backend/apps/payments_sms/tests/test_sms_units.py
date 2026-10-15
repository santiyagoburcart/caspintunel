"""Rial / Toman safety of SMS auto-confirm (incident 2026-10-15: an invoice of
175,662 Toman was approved by a Blu SMS of 175,662 RIAL = 17,566.2 Toman).

The SMS amount is converted to tomans exactly once with an explicit unit (from
the SMS text, else the bank number's setting) and must equal the invoice
exactly. Unit look-alikes are never approved — they are logged as
"amount mismatch" for a manual check."""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Staff, User
from apps.adminpanel.tokens import issue_tokens
from apps.orders.models import Order, OrderStatus
from apps.orders.services import create_order
from apps.payments_sms.models import Payment, SmsAppDevice, SmsMessage, SmsSource
from apps.payments_sms.parsing import RIAL, TOMAN, deposit_amount
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db(transaction=True)

BLU = "بلو\nواریز پول\nپویا عزیز،{amount} ریال به حساب شخصی شما نشست.\nموجودی: 181,743,192 ریال\n17:55\n0723"
NO_UNIT = "بانک نمونه\nواریز\n+{amount}\nمانده: 12,345,678"


@pytest.fixture(autouse=True)
def no_fulfilment(monkeypatch):
    from apps.orders import tasks

    monkeypatch.setattr(tasks.fulfill_order, "delay", lambda *_: None)


@pytest.fixture
def device():
    return SmsAppDevice.objects.create(name="phone", is_active=True)


@pytest.fixture
def source():
    return SmsSource.objects.create(phone_number="+989999987641", description="blu")   # default unit: rial


def make_order(amount, name="c1"):
    user = User.objects.create_user(f"u-{name}", "Str0ngPass!")
    plan = Plan.objects.create(name_fa="p", price=Decimal("100000"), data_limit=1024**3, duration_days=30)
    o = create_order(user=user, plan_id=plan.id, requested_account_name=name)
    Order.objects.filter(pk=o.pk).update(amount_unique=Decimal(amount), amount_unique_lock=Decimal(amount))
    o.refresh_from_db()
    return o


def post(device, text, sender="+989999987641"):
    c = APIClient(); c.credentials(HTTP_X_DEVICE_TOKEN=device.api_token)
    r = c.post("/api/v1/payments/sms/inbound/", {"text": text, "sender": sender}, format="json")
    assert r.status_code == 201, r.data
    return r.data


def status(o):
    o.refresh_from_db()
    return o.status


# --- the incident ---------------------------------------------------------------
def test_incident_rial_sms_with_the_invoice_number_is_not_approved(device, source):
    order = make_order(175662)
    data = post(device, BLU.format(amount="175,662"))          # 175,662 RIAL = 17,566.2 T
    assert data["matched"] is False and data["reason"] == "amount mismatch"
    assert status(order) == OrderStatus.PENDING_PAYMENT and not Payment.objects.exists()
    msg = SmsMessage.objects.get()
    assert msg.note.startswith("amount mismatch") and f"order #{order.id}" in msg.note
    assert msg.parsed_raw == 175662 and msg.parsed_unit == RIAL and msg.parsed_amount is None


def test_one_tenth_underpayment_never_approves(device, source):
    order = make_order(175660)
    data = post(device, BLU.format(amount="175,660"))          # 17,566 T paid for a 175,660 T invoice
    assert data["matched"] is False and data["reason"] == "amount mismatch"
    assert status(order) == OrderStatus.PENDING_PAYMENT and not Payment.objects.exists()


def test_exact_rial_amount_approves_the_toman_invoice(device, source):
    order = make_order(175660)
    data = post(device, BLU.format(amount="1,756,600"))        # 1,756,600 Rial = 175,660 T
    assert data["matched"] is True and data["order_id"] == order.id
    assert Payment.objects.get(order=order).amount == Decimal("175660")
    assert status(order) == OrderStatus.PAID


def test_ten_times_overpayment_never_auto_approves(device, source):
    order = make_order(17566)
    data = post(device, BLU.format(amount="1,756,600"))        # 175,660 T for a 17,566 T invoice
    assert data["matched"] is False and data["reason"] == "amount mismatch"
    assert status(order) == OrderStatus.PENDING_PAYMENT


def test_toman_sms_must_match_exactly(device, source):
    order = make_order(250430)
    assert post(device, "واریز 25,043 تومان")["matched"] is False      # a tenth, in tomans
    assert status(order) == OrderStatus.PENDING_PAYMENT
    assert post(device, "واریز 250,430 تومان")["matched"] is True
    assert status(order) == OrderStatus.PAID


def test_one_toman_short_is_not_approved(device, source):
    order = make_order(250430)
    data = post(device, BLU.format(amount="2,504,290"))        # 250,429 T
    assert data["matched"] is False and status(order) == OrderStatus.PENDING_PAYMENT


# --- unit from the bank-number setting --------------------------------------------
def test_unknown_unit_uses_the_source_setting_rial(device, source):
    order = make_order(250430)
    assert post(device, NO_UNIT.format(amount="250,430"))["matched"] is False   # read as 25,043 T
    assert status(order) == OrderStatus.PENDING_PAYMENT
    assert post(device, NO_UNIT.format(amount="2,504,300"))["matched"] is True
    m = SmsMessage.objects.order_by("id").last()
    assert m.parsed_unit == RIAL and "bank-number setting" in m.note


def test_unknown_unit_uses_the_source_setting_toman(device):
    SmsSource.objects.create(phone_number="+989999987641", amount_unit=TOMAN)
    order = make_order(250430)
    assert post(device, NO_UNIT.format(amount="2,504,300"))["matched"] is False  # 2,504,300 T ≠ 250,430 T
    assert post(device, NO_UNIT.format(amount="250,430"))["matched"] is True
    assert status(order) == OrderStatus.PAID


def test_unit_in_the_sms_wins_over_the_setting(device):
    SmsSource.objects.create(phone_number="+989999987641", amount_unit=TOMAN)
    order = make_order(175660)
    assert post(device, BLU.format(amount="175,660"))["matched"] is False         # says ریال
    assert status(order) == OrderStatus.PENDING_PAYMENT


# --- parsing --------------------------------------------------------------------
@pytest.mark.parametrize("text,raw,unit,toman", [
    ("واریز ۱٬۷۵۶٬۶۰۰ ریال", 1756600, RIAL, Decimal("175660")),           # Persian digits + Arabic comma
    ("واریز ١,٧٥٦,٦٠٠ ريال", 1756600, RIAL, Decimal("175660")),           # Arabic-Indic digits + Arabic yeh
    ("واریز 1.756.600 ریال", 1756600, RIAL, Decimal("175660")),           # dot thousands
    ("واریز 1,756,600 ریال", 1756600, RIAL, Decimal("175660")),
    ("واریز 1756600ریال", 1756600, RIAL, Decimal("175660")),              # no space before the unit
    ("Deposit 1,756,600 IRR", 1756600, RIAL, Decimal("175660")),
    ("deposit 1,756,600 Rials", 1756600, RIAL, Decimal("175660")),
    ("واریز ۱۷۵٬۶۶۰ تومان", 175660, TOMAN, Decimal("175660")),
    ("Deposit 175,660 Toman", 175660, TOMAN, Decimal("175660")),
    ("واریز 175,662 ریال", 175662, RIAL, Decimal("17566.2")),             # not a whole toman amount
])
def test_units_digits_and_separators(text, raw, unit, toman):
    a = deposit_amount(text)
    assert (a.raw, a.unit, a.unit_from, a.toman) == (raw, unit, "sms", toman)


def test_balance_unit_counts_when_the_amount_line_has_none():
    a = deposit_amount("بلو\nواریز پول\n+2,500,000\nموجودی: 30,000,000 ریال", source_unit=TOMAN)
    assert (a.unit, a.unit_from, a.toman) == (RIAL, "sms", Decimal("250000"))


def test_conflicting_units_fall_back_to_the_setting():
    a = deposit_amount("واریز\n+2,500,000\nموجودی 3,000,000 ریال (300,000 تومان)", source_unit=RIAL)
    assert (a.unit, a.unit_from) == (RIAL, "source")


def test_no_lenient_helpers_left():
    from apps.payments_sms import matching, parsing

    assert not hasattr(parsing, "candidate_amounts") and not hasattr(parsing, "primary_amount_toman")
    assert not hasattr(matching, "candidate_amounts")


# --- admin ----------------------------------------------------------------------
def test_admin_sets_the_unit_and_sees_mismatches(device, source):
    boss = Staff(username="boss", is_superadmin=True); boss.set_password("x-Str0ng!"); boss.save()
    c = APIClient(); c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(boss)['access']}")
    assert c.get("/api/v1/admin/sms-sources/").json()["results"][0]["amount_unit"] == RIAL
    assert c.patch(f"/api/v1/admin/sms-sources/{source.id}/", {"amount_unit": "toman"}, format="json").status_code == 200
    assert c.patch(f"/api/v1/admin/sms-sources/{source.id}/", {"amount_unit": "dollar"}, format="json").status_code == 400
    c.patch(f"/api/v1/admin/sms-sources/{source.id}/", {"amount_unit": "rial"}, format="json")
    make_order(175662)
    post(device, BLU.format(amount="175,662"))
    post(device, "واریز 999,999,990 ریال")
    rows = c.get("/api/v1/admin/sms-log/?matched=mismatch").json()["results"]
    assert len(rows) == 1 and rows[0]["parsed_raw"] == 175662 and rows[0]["parsed_unit"] == "rial"
    assert rows[0]["note"].startswith("amount mismatch")
