"""Blu Bank deposits pushed by the Iran-side collector: signed webhook, idempotent
storage, exact-amount auto-confirm inside the order's time window (same rules as SMS),
duplicates after an SMS, near-miss review, staff attach, collector health alerts.
Nothing here talks to a bank: batches are built in the test and signed with a test secret."""
import json
import time
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, Staff, User
from apps.adminpanel.tokens import issue_tokens
from apps.orders.models import Order, OrderStatus
from apps.orders.services import create_order
from apps.payments_sms.blu import check_stale, sign
from apps.payments_sms.models import (
    BluCollector,
    BluStatus,
    BluTransaction,
    ConfirmedBy,
    Payment,
    PaymentMethod,
    PaymentStatus,
    SmsAppDevice,
    SmsSource,
)
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db(transaction=True)

URL = "/api/v1/payments/blu/webhook/"
SECRET = "t" * 40 + "-blu-test-secret"
INVOICE = 175662


@pytest.fixture(autouse=True)
def env(monkeypatch, settings):
    from apps.common import staff_alert
    from apps.notifications import live
    from apps.orders import tasks

    settings.BLU_PUSH_SECRET = SECRET
    settings.BLU_LATE_GRACE_MINUTES = 30
    settings.BLU_STALE_MINUTES = 15
    monkeypatch.setattr(tasks.fulfill_order, "delay", lambda *_: None)
    events, alerts = [], []
    monkeypatch.setattr(live, "push_payments_event", lambda event, **d: events.append((event, d)))
    monkeypatch.setattr(staff_alert, "alert_staff", lambda text, **kw: alerts.append((text, kw)) or 1)
    return {"events": events, "alerts": alerts}


def make_order(amount=INVOICE, name="c1"):
    user = User.objects.create_user(f"u-{name}", "Str0ngPass!")
    plan = Plan.objects.create(name_fa="p", price=Decimal("100000"), data_limit=1024**3, duration_days=30)
    o = create_order(user=user, plan_id=plan.id, requested_account_name=name)
    Order.objects.filter(pk=o.pk).update(amount_unique=Decimal(amount), amount_unique_lock=Decimal(amount))
    o.refresh_from_db()
    return o


def item(toman=INVOICE, *, irr=None, at=None, **extra):
    data = {
        "id": extra.pop("id", None) or f"blu-{uuid.uuid4().hex}",
        "direction": "بستانکار", "type": "دریافت از کارت",
        "amount_irr": irr if irr is not None else toman * 10, "balance_after_irr": 12452596,
        "timestamp": int((at or timezone.now()).timestamp()), "jalali_date": "1405/8/9", "time": "10:20:39",
        "account_iban": "IR000000000000000000000000", "receipt": "249042", "reference": "325456982691",
        "counterparty_name": "پویا", "payer_card": "603799******5440", "payer_card_last4": "5440",
        "payer_card_first6": "603799", "status": "رسید",
    }
    data.update(extra)
    return data


def post(items, *, secret=SECRET, ts=None, sig=None, raw=None, headers=True):
    body = raw if raw is not None else json.dumps({"source": "blu", "batch_id": "b1", "items": items}).encode()
    ts = str(int(time.time())) if ts is None else ts
    kw = {}
    if headers:
        kw = {"HTTP_X_BLU_TIMESTAMP": ts, "HTTP_X_BLU_SIGNATURE": sig if sig is not None else sign(secret, ts, body),
              "HTTP_X_BLU_BATCH_ID": str(uuid.uuid4())}
    return APIClient().post(URL, data=body, content_type="application/json", **kw)


def staff_client(codes, name):
    if codes == "super":
        s = Staff(username=name, is_superadmin=True)
    else:
        role = Role.objects.create(name=f"blu-{name}")
        role.permissions.set([Permission.objects.get_or_create(code=c, defaults={"name": c})[0] for c in codes])
        s = Staff(username=name, role=role)
    s.set_password("x-Str0ng!"); s.save()
    c = APIClient(); c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    return c


# --- signature / feature switch ------------------------------------------------------
def test_feature_disabled_returns_503(settings):
    settings.BLU_PUSH_SECRET = ""
    assert post([]).status_code == 503
    settings.BLU_PUSH_SECRET = "too-short"          # < 32 chars counts as off
    assert post([]).status_code == 503


@pytest.mark.parametrize("case", ["missing", "bad_sig", "wrong_secret", "stale", "future", "not_digits"])
def test_bad_signature_is_403(case):
    now = int(time.time())
    if case == "missing":
        r = post([item()], headers=False)
    elif case == "bad_sig":
        r = post([item()], sig="0" * 64)
    elif case == "wrong_secret":
        r = post([item()], secret="x" * 48)
    elif case == "stale":
        r = post([item()], ts=str(now - 301))
    elif case == "future":
        r = post([item()], ts=str(now + 301))
    else:
        r = post([item()], ts="12a4")
    assert r.status_code == 403
    assert BluTransaction.objects.count() == 0


def test_signature_covers_the_raw_body():
    body = json.dumps({"items": [item()]}).encode()
    ts = str(int(time.time()))
    sig = sign(SECRET, ts, body)
    tampered = body.replace(b"175662", b"175663")
    r = APIClient().post(URL, data=tampered, content_type="application/json",
                         HTTP_X_BLU_TIMESTAMP=ts, HTTP_X_BLU_SIGNATURE=sig)
    assert r.status_code == 403


def test_malformed_json_or_no_items_is_400():
    assert post(None, raw=b"{not json").status_code == 400
    assert post(None, raw=json.dumps({"source": "blu"}).encode()).status_code == 400
    assert post(None, raw=json.dumps({"items": {"a": 1}}).encode()).status_code == 400


# --- storage ------------------------------------------------------------------------
def test_valid_batch_is_stored_and_retry_is_idempotent():
    items = [item(1000, id="A1"), item(2000, id="A2")]
    r = post(items)
    assert r.status_code == 200 and r.json() == {"ok": True, "received": 2, "created": 2}
    r = post(items)                                     # the collector retries the same batch
    assert r.status_code == 200 and r.json() == {"ok": True, "received": 2, "created": 0}
    assert BluTransaction.objects.count() == 2
    tx = BluTransaction.objects.get(bank_id="A1")
    assert tx.amount_irr == 10000 and tx.amount_toman == 1000
    assert tx.receipt == "249042" and tx.reference == "325456982691" and tx.payer_last4 == "5440"


def test_empty_batch_is_a_heartbeat():
    r = post([])
    assert r.status_code == 200 and r.json()["created"] == 0
    c = BluCollector.get()
    assert c.last_batch_at is not None and c.batches == 1


def test_bad_item_is_skipped_not_4xx():
    r = post([{"id": "x"}, "junk", item(1000, id="GOOD")])
    assert r.status_code == 200 and r.json()["created"] == 1
    assert list(BluTransaction.objects.values_list("bank_id", flat=True)) == ["GOOD"]


def test_debit_item_is_ignored():
    o = make_order()
    post([item(INVOICE, id="D1", direction="بدهکار")])
    tx = BluTransaction.objects.get(bank_id="D1")
    assert tx.status == BluStatus.IGNORED
    o.refresh_from_db()
    assert o.status == OrderStatus.PENDING_PAYMENT and not Payment.objects.filter(order=o).exists()


def test_full_card_numbers_are_masked_everywhere():
    post([item(1000, id="C1", payer_card="6037991234565440", description="از کارت 6037-9912-3456-5440",
               cards_in_description=["6037991234565440"])])
    tx = BluTransaction.objects.get(bank_id="C1")
    assert tx.payer_card == "603799******5440"
    assert "1234" not in json.dumps(tx.raw, ensure_ascii=False)
    rows = staff_client("super", "boss").get("/api/v1/admin/payments/blu-transactions/").json()["results"]
    assert rows[0]["payer_card"] == "603799******5440"


# --- matching -----------------------------------------------------------------------
def test_exact_amount_in_window_auto_confirms(env):
    o = make_order()
    post([item(INVOICE, id="M1")])
    o.refresh_from_db()
    assert o.status in (OrderStatus.PAID, OrderStatus.COMPLETED)
    p = Payment.objects.get(order=o)
    assert p.status == PaymentStatus.APPROVED and p.method == PaymentMethod.BLU_AUTO
    assert p.confirmed_by == ConfirmedBy.SYSTEM and p.blu_transaction.bank_id == "M1"
    assert p.receipt_ref == "325456982691"
    tx = BluTransaction.objects.get(bank_id="M1")
    assert tx.status == BluStatus.MATCHED and tx.matched_order_id == o.id and tx.matched_payment_id == p.id
    assert ("blu_approved", {"order_id": o.id, "payment_id": p.id}) in env["events"]


def test_amount_not_whole_toman_stays_unmatched():
    o = make_order()
    post([item(irr=INVOICE * 10 + 3, id="R1")])
    tx = BluTransaction.objects.get(bank_id="R1")
    assert tx.status == BluStatus.UNMATCHED and tx.amount_toman is None and "whole toman" in tx.match_note
    o.refresh_from_db()
    assert o.status == OrderStatus.PENDING_PAYMENT


def test_deposit_before_the_order_existed_is_not_matched():
    """A unique amount is reused after its reservation ends: an old deposit must not pay a new order."""
    o = make_order()
    post([item(INVOICE, id="OLD", at=timezone.now() - timedelta(hours=1))])
    tx = BluTransaction.objects.get(bank_id="OLD")
    assert tx.status == BluStatus.UNMATCHED and "outside its window" in tx.match_note
    o.refresh_from_db()
    assert o.status == OrderStatus.PENDING_PAYMENT and not Payment.objects.filter(order=o).exists()


def test_after_sms_approval_the_deposit_is_a_duplicate():
    SmsSource.objects.create(phone_number="+989999987641", description="blu")
    device = SmsAppDevice.objects.create(name="iPhone", is_active=True)
    o = make_order()
    c = APIClient(); c.credentials(HTTP_X_DEVICE_TOKEN=device.api_token)
    sms = f"بلو\nواریز پول\nپویا عزیز،{INVOICE * 10:,} ریال به حساب شخصی شما نشست.\nموجودی: 1 ریال"
    assert c.post("/api/v1/payments/sms/inbound/", {"text": sms, "sender": "+989999987641"},
                  format="json").data["matched"] is True
    post([item(INVOICE, id="DUP")])
    tx = BluTransaction.objects.get(bank_id="DUP")
    assert tx.status == BluStatus.DUPLICATE and tx.matched_order_id == o.id
    assert Payment.objects.filter(order=o).count() == 1
    assert Payment.objects.get(order=o).method == PaymentMethod.SMS_AUTO


def test_blu_first_then_sms_does_not_confirm_twice():
    SmsSource.objects.create(phone_number="+989999987641", description="blu")
    device = SmsAppDevice.objects.create(name="iPhone", is_active=True)
    o = make_order()
    post([item(INVOICE, id="FIRST")])
    c = APIClient(); c.credentials(HTTP_X_DEVICE_TOKEN=device.api_token)
    sms = f"بلو\nواریز پول\nپویا عزیز،{INVOICE * 10:,} ریال به حساب شخصی شما نشست.\nموجودی: 1 ریال"
    assert c.post("/api/v1/payments/sms/inbound/", {"text": sms, "sender": "+989999987641"},
                  format="json").data["matched"] is False
    p = Payment.objects.get(order=o)
    assert p.method == PaymentMethod.BLU_AUTO and Payment.objects.count() == 1


def test_near_amount_is_flagged_not_approved(env):
    o = make_order()
    post([item(170000, id="NEAR")])
    o.refresh_from_db()
    assert o.status == OrderStatus.PENDING_PAYMENT
    p = Payment.objects.get(order=o)
    assert p.status == PaymentStatus.PENDING and p.method == PaymentMethod.BLU_MISMATCH
    tx = BluTransaction.objects.get(bank_id="NEAR")
    assert tx.status == BluStatus.UNMATCHED and tx.matched_order_id == o.id and "mismatch" in tx.match_note
    assert [e for e, _ in env["events"] if e.startswith("blu_")] == ["blu_mismatch"]
    assert any("مبلغ نامطابق" in text for text, _ in env["alerts"])
    # the payments queue shows it with the deposit vs invoice
    rows = staff_client("super", "boss").get("/api/v1/admin/payments/pending/").json()["results"]
    mm = rows[0]["sms_mismatch"]
    assert mm["source"] == "blu" and mm["kind"] == "less" and Decimal(mm["sms_amount"]) == 170000


def test_staff_approving_a_flagged_deposit_marks_it_matched():
    o = make_order()
    post([item(170000, id="NEAR2")])
    p = Payment.objects.get(order=o)
    r = staff_client("super", "boss").post(f"/api/v1/admin/payments/{p.id}/approve/", {}, format="json")
    assert r.status_code == 200, r.content
    tx = BluTransaction.objects.get(bank_id="NEAR2")
    assert tx.status == BluStatus.MATCHED and tx.matched_payment_id == p.id


def test_no_order_stays_unmatched_and_is_never_matched_later():
    post([item(123456, id="LONE")])
    tx = BluTransaction.objects.get(bank_id="LONE")
    assert tx.status == BluStatus.UNMATCHED and "no pending order" in tx.match_note
    o = make_order(123456, "late")                      # a new order with that amount
    post([item(123456, id="LONE")])                     # collector retry: row untouched
    o.refresh_from_db()
    assert o.status == OrderStatus.PENDING_PAYMENT


def test_bank_reference_feeds_duplicate_receipt_warning():
    o1 = make_order(INVOICE, "a")
    post([item(INVOICE, id="REF1")])
    o2 = make_order(200001, "b")
    Payment.objects.create(order=o2, method=PaymentMethod.CARD_MANUAL, amount=o2.amount_unique,
                           status=PaymentStatus.PENDING, receipt_ref="325456982691")
    rows = staff_client("super", "boss").get("/api/v1/admin/payments/pending/").json()["results"]
    kinds = {w["kind"]: w for w in rows[0]["warnings"]}
    assert "duplicate_ref" in kinds
    assert kinds["duplicate_ref"]["payments"][0]["order_id"] == o1.id


# --- admin list + attach ------------------------------------------------------------
def test_admin_list_needs_payment_view_and_shows_health():
    post([item(1000, id="L1")])
    assert staff_client([], "nobody").get("/api/v1/admin/payments/blu-transactions/").status_code == 403
    r = staff_client(["payment.view"], "viewer").get("/api/v1/admin/payments/blu-transactions/?status=unmatched")
    assert r.status_code == 200
    body = r.json()
    assert body["collector"]["connected"] is True and body["collector"]["enabled"] is True
    assert body["results"][0]["id"] and body["counts"]["unmatched"] == 1


def test_attach_requires_payment_approve_and_approves():
    post([item(99999, id="ATT")])
    tx = BluTransaction.objects.get(bank_id="ATT")
    o = make_order(INVOICE, "att")
    url = f"/api/v1/admin/payments/blu-transactions/{tx.id}/attach/"
    assert staff_client(["payment.view"], "viewer").post(url, {"order_id": o.id}, format="json").status_code == 403
    approver = staff_client(["payment.view", "payment.approve"], "approver")
    r = approver.post(url, {"order_id": o.id}, format="json")
    assert r.status_code == 200, r.content
    p = Payment.objects.get(order=o)
    assert p.status == PaymentStatus.APPROVED and p.method == PaymentMethod.BLU_AUTO
    assert p.confirmed_by == ConfirmedBy.ADMIN and p.confirmed_by_staff.username == "approver"
    tx.refresh_from_db()
    assert tx.status == BluStatus.MATCHED and tx.matched_order_id == o.id
    # a second attach (or to a paid order) is refused
    assert approver.post(url, {"order_id": o.id}, format="json").status_code == 409


# --- collector health ---------------------------------------------------------------
def test_stale_collector_alerts_once_then_recovers(env):
    assert check_stale() == "never"                      # never spoke: nothing to alert
    post([])
    assert check_stale() == "ok"
    BluCollector.objects.filter(pk=1).update(last_batch_at=timezone.now() - timedelta(minutes=20))
    assert check_stale() == "alert"
    assert check_stale() == "alerted"                    # one alert per outage
    assert sum("بلو" in t for t, _ in env["alerts"]) == 1
    assert ("blu_collector", {"connected": False, "minutes": 20}) in env["events"]
    post([])                                             # heartbeat again
    assert BluCollector.get().stale_alerted_at is None
    assert any("back online" in t for t, _ in env["alerts"])
