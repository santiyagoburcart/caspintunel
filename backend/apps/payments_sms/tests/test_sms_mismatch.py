"""Exact-only SMS auto-confirm + near-miss review (same endpoint for the iPhone
Shortcut and the Android app). An order is approved only when the deposit equals
the invoice EXACTLY; 1 toman less or more is never approved — it is linked to the
order as "less"/"more" for manual review (Payments queue + SMS log + live event)."""
from datetime import datetime, timezone as dt_tz
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Staff, User
from apps.adminpanel.tokens import issue_tokens
from apps.orders.models import Order, OrderStatus
from apps.orders.services import create_order
from apps.payments_sms.models import Payment, PaymentMethod, PaymentStatus, SmsAppDevice, SmsMessage, SmsSource
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db(transaction=True)

# Blu-style deposit SMS (amount in RIAL, as the bank writes it)
BLU = "بلو\nواریز پول\nپویا عزیز،{amount} ریال به حساب شخصی شما نشست.\nموجودی: 181,743,192 ریال\n17:55\n0723"
INVOICE = 175662


def ios_payload(text):      # iPhone Shortcut: JSON {text, sender}, header X-Device-Token
    return {"text": text, "sender": "+989999987641"}


def android_payload(text):  # Android SMS Bridge (Gson): + received_at
    return {"text": text, "sender": "+989999987641", "received_at": datetime.now(dt_tz.utc).isoformat()}


FORMATS = pytest.mark.parametrize("fmt", [ios_payload, android_payload], ids=["ios", "android"])


@pytest.fixture(autouse=True)
def env(monkeypatch):
    from apps.notifications import live
    from apps.orders import tasks

    monkeypatch.setattr(tasks.fulfill_order, "delay", lambda *_: None)
    events = []
    monkeypatch.setattr(live, "push_payments_event", lambda event, **d: events.append((event, d)))
    SmsSource.objects.create(phone_number="+989999987641", description="blu")      # unit: rial
    return events


@pytest.fixture
def device():
    return SmsAppDevice.objects.create(name="My Phone", is_active=True)


def make_order(amount=INVOICE, name="c1"):
    user = User.objects.create_user(f"u-{name}", "Str0ngPass!")
    plan = Plan.objects.create(name_fa="p", price=Decimal("100000"), data_limit=1024**3, duration_days=30)
    o = create_order(user=user, plan_id=plan.id, requested_account_name=name)
    Order.objects.filter(pk=o.pk).update(amount_unique=Decimal(amount), amount_unique_lock=Decimal(amount))
    o.refresh_from_db()
    return o


def send(device, payload):
    c = APIClient(); c.credentials(HTTP_X_DEVICE_TOKEN=device.api_token)
    r = c.post("/api/v1/payments/sms/inbound/", payload, format="json")
    assert r.status_code == 201, r.data
    return r.data


def rial(toman):
    return f"{toman * 10:,}"


def admin():
    s = Staff(username="boss", is_superadmin=True); s.set_password("x-Str0ng!"); s.save()
    c = APIClient(); c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    return c


@FORMATS
def test_exact_amount_is_approved(device, env, fmt):
    o = make_order()
    data = send(device, fmt(BLU.format(amount=rial(INVOICE))))
    o.refresh_from_db()
    assert data["matched"] is True and o.status != OrderStatus.PENDING_PAYMENT
    p = Payment.objects.get(order=o)
    assert p.status == PaymentStatus.APPROVED and p.method == PaymentMethod.SMS_AUTO
    assert [e for e, _ in env if e.startswith("sms_")] == ["sms_approved"]


@FORMATS
@pytest.mark.parametrize("delta,kind", [(-1, "less"), (1, "more")])
def test_one_toman_off_is_never_approved_but_flagged(device, env, fmt, delta, kind):
    o = make_order()
    data = send(device, fmt(BLU.format(amount=rial(INVOICE + delta))))
    o.refresh_from_db()
    assert data["matched"] is False and data["reason"] == "amount mismatch" and data["mismatch"] == kind
    assert o.status == OrderStatus.PENDING_PAYMENT                         # NOT approved / paid
    msg = SmsMessage.objects.get()
    assert msg.matched_order_id is None and msg.mismatch_order_id == o.id and msg.mismatch_kind == kind
    assert msg.note.startswith("amount mismatch") and ("LESS" if kind == "less" else "MORE") in msg.note
    p = Payment.objects.get(order=o)                                         # in the Payments queue, pending
    assert (p.status, p.method, p.sms_message_id, p.amount) == (PaymentStatus.PENDING, PaymentMethod.SMS_MISMATCH, msg.id, INVOICE)
    ev = [d for e, d in env if e == "sms_mismatch"]
    assert ev == [{"order_id": o.id, "payment_id": p.id, "kind": kind, "sms_amount": str(INVOICE + delta),
                   "invoice_amount": str(INVOICE)}]

    c = admin()
    row = c.get("/api/v1/admin/payments/pending/").json()["results"][0]
    assert row["order_id"] == o.id and row["sms_mismatch"]["kind"] == kind
    assert Decimal(row["sms_mismatch"]["sms_amount"]) == INVOICE + delta and Decimal(row["sms_mismatch"]["invoice_amount"]) == INVOICE
    log = c.get("/api/v1/admin/sms-log/?matched=mismatch").json()
    log = log.get("results", log)
    assert log[0]["mismatch_order"] == o.id and log[0]["mismatch_kind"] == kind and Decimal(log[0]["mismatch_invoice"]) == INVOICE

    # the admin decides: approving goes through approve_payment as usual
    assert c.post(f"/api/v1/admin/payments/{p.id}/approve/", {}, format="json").status_code == 200
    p.refresh_from_db(); assert p.status == PaymentStatus.APPROVED


@FORMATS
def test_far_amount_is_only_logged(device, env, fmt):
    o = make_order()
    data = send(device, fmt(BLU.format(amount=rial(INVOICE * 3))))
    assert data["matched"] is False and data["reason"] != "amount mismatch" and "mismatch" not in data
    msg = SmsMessage.objects.get()
    assert msg.mismatch_order_id is None and msg.matched_order_id is None
    assert not Payment.objects.filter(order=o).exists() and not [e for e, _ in env if e == "sms_mismatch"]


def test_twenty_percent_bounds_and_closest_order_wins(device, env):
    a, b = make_order(100000, "a"), make_order(110000, "b")
    send(device, ios_payload(BLU.format(amount=rial(108000))))                 # closer to b (2,000 vs 8,000)
    assert SmsMessage.objects.latest("id").mismatch_order_id == b.id
    send(device, ios_payload(BLU.format(amount=rial(140000))))                 # > b +20 % (132,000) → far
    assert SmsMessage.objects.latest("id").mismatch_order_id is None
    send(device, ios_payload(BLU.format(amount=rial(80000))))                  # exactly a -20 % → near (less)
    m = SmsMessage.objects.latest("id"); assert (m.mismatch_order_id, m.mismatch_kind) == (a.id, "less")


def test_unit_case_x10_is_flagged_not_approved(device, env):
    o = make_order()
    send(device, ios_payload(BLU.format(amount=f"{INVOICE:,}")))                # 175,662 RIAL vs 175,662 T invoice
    o.refresh_from_db(); m = SmsMessage.objects.get()
    assert o.status == OrderStatus.PENDING_PAYMENT and (m.mismatch_order_id, m.mismatch_kind) == (o.id, "less")


def test_pending_receipt_gets_the_sms_attached_not_replaced(device, env):
    o = make_order()
    p = Payment.objects.create(order=o, method=PaymentMethod.CARD_MANUAL, amount=INVOICE, status=PaymentStatus.PENDING)
    send(device, android_payload(BLU.format(amount=rial(INVOICE - 1))))
    p.refresh_from_db()
    assert p.method == PaymentMethod.CARD_MANUAL and p.status == PaymentStatus.PENDING and p.sms_message_id == SmsMessage.objects.get().id
    assert Payment.objects.filter(order=o).count() == 1
