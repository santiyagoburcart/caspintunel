"""Offline SMS queue upload (iPhone Shortcut v1.1): POST sms/inbound-batch/.
Batch dedupe, idempotent approval, matching at received_at (late SMS, orders
that expired while the SMS waited in the phone), refused items, NDJSON with
Persian text and newlines, multipart file, admin SMS log fields."""
import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.adminpanel.tests.conftest import perms, staff_client, superadmin  # noqa: F401 — fixtures
from apps.common.models import AuditLog
from apps.orders.models import Order, OrderStatus
from apps.orders.services import create_order, expire_stale_reservations
from apps.payments_sms.batch import key_for, parse_body, parse_time
from apps.payments_sms.models import Payment, PaymentStatus, SmsAppDevice, SmsMessage
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db
URL = "/api/v1/payments/sms/inbound-batch/"


@pytest.fixture
def device():
    return SmsAppDevice.objects.create(name="iphone", is_active=True)


@pytest.fixture
def plan():
    return Plan.objects.create(name_fa="p", price=Decimal("100000"), data_limit=1024**3, duration_days=30)


@pytest.fixture(autouse=True)
def no_fulfil(monkeypatch):
    """count fulfilment dispatches instead of provisioning"""
    from apps.orders import tasks

    calls = []
    monkeypatch.setattr(tasks.fulfill_order, "delay", lambda oid: calls.append(oid))
    return calls


def _order(plan, name="cust-1", *, minutes_ago=0, user=None):
    user = user or User.objects.create_user(f"u-{name}", "Str0ngPass!")
    o = create_order(user=user, plan_id=plan.id, requested_account_name=name)
    if minutes_ago:
        t = timezone.now() - timedelta(minutes=minutes_ago)
        Order.objects.filter(pk=o.pk).update(created_at=t, unique_expire_at=t + timedelta(minutes=30))
        o.refresh_from_db()
    return o


def _sms(amount_toman, at, *, text=None, sender="+985000"):
    return {"text": text or f"بانک رسالت\nواریز {int(amount_toman) * 10:,} ریال\nمانده ۱۲۳", "sender": sender,
            "received_at": at.isoformat()}


def _post(device, body, *, content_type="text/plain", run_on_commit=None):
    c = APIClient()
    c.credentials(HTTP_X_DEVICE_TOKEN=device.api_token)
    data = body if isinstance(body, (str, bytes)) else json.dumps(body, ensure_ascii=False)
    if run_on_commit:
        with run_on_commit(execute=True):
            return c.generic("POST", URL, data, content_type=content_type)
    return c.generic("POST", URL, data, content_type=content_type)


def ndjson(*items):
    return "\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n"


# ------------------------------------------------------------------ parsing
def test_ndjson_with_persian_text_and_newlines(device):
    now = timezone.now()
    a = {"text": "سلام\nخط دوم «واریز» ۱۲٬۰۰۰", "sender": "رسالت", "received_at": (now - timedelta(minutes=3)).isoformat()}
    b = {"text": "second\r\nwith CRLF", "sender": "", "received_at": now.strftime("%Y-%m-%dT%H:%M:%S%z")}  # +0000
    pretty = json.dumps({"text": "pretty ✓", "received_at": now.isoformat()}, ensure_ascii=False, indent=2)
    body = "﻿" + json.dumps(a, ensure_ascii=False) + "\n\n" + json.dumps(b) + pretty   # BOM, blank line, no newline
    r = _post(device, body)
    assert r.status_code == 200 and r.data["ok"] is True and r.data["result"] == "stored"
    assert (r.data["count"], r.data["new"]) == (3, 3)
    texts = list(SmsMessage.objects.order_by("id").values_list("raw_text", flat=True))
    assert a["text"] in texts and "second\r\nwith CRLF" in texts and "pretty ✓" in texts
    m = SmsMessage.objects.get(raw_text=a["text"])
    assert m.sender == "رسالت" and abs((m.received_at - (now - timedelta(minutes=3))).total_seconds()) < 1
    assert m.dedupe_key and m.uploaded_at >= m.received_at


def test_parser_accepts_an_array_and_reports_bad_lines():
    items = parse_body('[{"text": "a"}, {"text": "b"}]\n{"text": "c"}\nnot json\n{"text": "d"}')
    assert [i["text"] if isinstance(i, dict) else i[0] for i in items] == ["a", "b", "c", "bad", "d"]
    assert parse_time("2026-10-24T18:12:03+0330").utcoffset() == timedelta(hours=3, minutes=30)
    assert parse_time("2026-10-24T14:42:03Z").hour == 14 and parse_time("yesterday") is None


# ------------------------------------------------------------------ dedupe + idempotent approval
def test_resending_the_queue_never_processes_an_sms_twice(device, plan, no_fulfil, django_capture_on_commit_callbacks):
    order = _order(plan)
    now = timezone.now()
    body = ndjson(_sms(order.amount_unique, now - timedelta(minutes=1)), _sms(999, now - timedelta(minutes=2)))
    r1 = _post(device, body, run_on_commit=django_capture_on_commit_callbacks)
    assert r1.data["ok"] and (r1.data["new"], r1.data["matched"]) == (2, 1)
    first = r1.data["results"][0]
    assert first["status"] == "new" and first["matched"] is True and first["order_id"] == order.id
    assert r1.data["results"][1]["status"] == "new" and r1.data["results"][1]["matched"] is False
    assert r1.data["results"][1]["reason"]
    # the shortcut lost the answer ("The network connection was lost") and sends the same queue again
    r2 = _post(device, body + body, run_on_commit=django_capture_on_commit_callbacks)  # even twice in one batch
    assert r2.data["ok"] and r2.data["result"] == "stored"
    assert (r2.data["new"], r2.data["duplicate"], r2.data["matched"]) == (0, 4, 0)
    assert SmsMessage.objects.count() == 2
    assert Payment.objects.filter(order=order, status=PaymentStatus.APPROVED).count() == 1
    assert AuditLog.objects.filter(action="payment.sms_auto_confirmed").count() == 1
    assert no_fulfil == [order.id]                                        # fulfilled once
    order.refresh_from_db()
    assert order.status == OrderStatus.PAID


def test_the_same_sms_twice_in_one_batch_is_stored_once(device, plan):
    order = _order(plan)
    s = _sms(order.amount_unique, timezone.now())
    r = _post(device, [s, s])
    assert [x["status"] for x in r.data["results"]] == ["new", "duplicate"]
    assert Payment.objects.filter(order=order).count() == 1


def test_dedupe_is_per_device(device, plan):
    other = SmsAppDevice.objects.create(name="ipad", is_active=True)
    s = _sms(5, timezone.now())
    assert _post(device, [s]).data["new"] == 1 and _post(other, [s]).data["new"] == 1
    at = parse_time(s["received_at"])
    assert key_for(device.id, at, s["text"]) != key_for(other.id, at, s["text"])


# ------------------------------------------------------------------ matching at received_at
def test_late_sms_matches_the_order_that_expired_while_it_was_queued(device, plan, no_fulfil,
                                                                    django_capture_on_commit_callbacks):
    order = _order(plan, minutes_ago=120)                  # deadline was 90 minutes ago
    expire_stale_reservations()
    order.refresh_from_db()
    assert order.status == OrderStatus.EXPIRED and order.amount_unique_lock is None
    arrived = order.created_at + timedelta(minutes=10)     # paid in time, uploaded 110 minutes later
    r = _post(device, [_sms(order.amount_unique, arrived)], run_on_commit=django_capture_on_commit_callbacks)
    res = r.data["results"][0]
    assert res["matched"] is True and res["order_id"] == order.id and res["late"] is True
    order.refresh_from_db()
    assert order.status == OrderStatus.PAID and no_fulfil == [order.id]
    msg = SmsMessage.objects.get(pk=res["message_id"])
    assert msg.delivered_late and "delivered late" in msg.note
    assert abs((msg.received_at - arrived).total_seconds()) < 1


def test_expired_order_whose_amount_was_reused_is_paid_not_the_new_one(device, plan, no_fulfil):
    old = _order(plan, "old-1", minutes_ago=120)
    expire_stale_reservations()
    new = _order(plan, "new-1")
    Order.objects.filter(pk=new.pk).update(amount_unique=old.amount_unique, amount_unique_lock=old.amount_unique)
    r = _post(device, [_sms(old.amount_unique, old.created_at + timedelta(minutes=5))])
    assert r.data["results"][0]["order_id"] == old.id
    old.refresh_from_db(); new.refresh_from_db()
    assert old.status == OrderStatus.PAID and old.amount_unique_lock is None        # paid without stealing the lock
    assert new.status == OrderStatus.PENDING_PAYMENT and new.amount_unique_lock == old.amount_unique


def test_sms_after_the_deadline_or_before_the_order_does_not_match(device, plan):
    expired = _order(plan, "exp-1", minutes_ago=120)
    expire_stale_reservations()
    after = expired.unique_expire_at + timedelta(minutes=10)
    r = _post(device, [_sms(expired.amount_unique, after)])
    assert r.data["results"][0]["matched"] is False
    expired.refresh_from_db()
    assert expired.status == OrderStatus.EXPIRED and not Payment.objects.filter(order=expired).exists()
    # an order created after the SMS arrived can never be paid by it
    fresh = _order(plan, "fresh-1")
    r = _post(device, [_sms(fresh.amount_unique, fresh.created_at - timedelta(minutes=30))])
    assert r.data["results"][0]["matched"] is False
    fresh.refresh_from_db()
    assert fresh.status == OrderStatus.PENDING_PAYMENT


def test_order_dropped_early_for_a_newer_one_is_not_paid_by_a_later_sms(device, plan):
    """_drop_reservation expires an order before its deadline; its amount may go to a new order"""
    from apps.orders.services import _drop_reservation

    dropped = _order(plan, "drop-1", minutes_ago=5)
    _drop_reservation(dropped)
    new = _order(plan, "new-2")
    Order.objects.filter(pk=new.pk).update(amount_unique=dropped.amount_unique, amount_unique_lock=dropped.amount_unique)
    r = _post(device, [_sms(dropped.amount_unique, timezone.now())])
    assert r.data["results"][0]["order_id"] == new.id
    dropped.refresh_from_db()
    assert dropped.status == OrderStatus.EXPIRED


def test_near_miss_of_a_late_sms_goes_to_manual_review(device, plan):
    order = _order(plan, minutes_ago=60)
    expire_stale_reservations()
    r = _post(device, [_sms(order.amount_unique - 5000, order.created_at + timedelta(minutes=3))])
    res = r.data["results"][0]
    assert res["matched"] is False and res["reason"] == "amount mismatch" and res["order_id"] == order.id
    p = Payment.objects.get(order=order)
    assert p.status == PaymentStatus.PENDING and p.method == "sms_mismatch"      # never approved


# ------------------------------------------------------------------ refused items
def test_future_old_and_broken_items_are_refused_with_a_reason_and_logged(device):
    now = timezone.now()
    body = ndjson(
        {"text": "واریز", "received_at": (now + timedelta(hours=1)).isoformat()},
        {"text": "واریز", "received_at": (now - timedelta(hours=73)).isoformat()},
        {"text": "واریز"},
        {"text": "", "received_at": now.isoformat()},
    ) + "{broken json\n"
    r = _post(device, body)
    assert r.status_code == 200 and r.data["ok"] is True                # the queue can still be cleared
    reasons = [x["reason"] for x in r.data["results"]]
    assert [x["status"] for x in r.data["results"]] == ["refused"] * 5
    assert "future" in reasons[0] and "72 hours" in reasons[1] and "received_at missing" in reasons[2]
    assert "empty text" in reasons[3] and "not valid JSON" in reasons[4]
    assert SmsMessage.objects.filter(note__startswith="refused (batch upload)").count() == 5
    assert not Payment.objects.exists()
    again = _post(device, body)
    assert [x["status"] for x in again.data["results"]] == ["duplicate"] * 5 and SmsMessage.objects.count() == 5


# ------------------------------------------------------------------ transport
def test_auth_and_multipart_file(device, plan):
    c = APIClient()
    assert c.post(URL, "[]", content_type="application/json").status_code == 401
    order = _order(plan)
    f = SimpleUploadedFile("CaspinSMS-queue.txt", ndjson(_sms(order.amount_unique, timezone.now())).encode(),
                           content_type="text/plain")
    c.credentials(HTTP_X_DEVICE_TOKEN=device.api_token)
    r = c.post(URL, {"queue": f}, format="multipart")
    assert r.data["ok"] and r.data["matched"] == 1
    assert _post(device, "").data == {"ok": True, "result": "stored", "count": 0, "new": 0, "duplicate": 0,
                                      "refused": 0, "matched": 0, "results": []}


def test_old_single_endpoint_still_works(device, plan):
    order = _order(plan)
    c = APIClient()
    c.credentials(HTTP_X_DEVICE_TOKEN=device.api_token)
    r = c.post("/api/v1/payments/sms/inbound/", {"text": f"واریز {int(order.amount_unique) * 10} ریال"}, format="json")
    assert r.status_code == 201 and r.data["matched"] is True
    m = SmsMessage.objects.get()
    assert m.dedupe_key is None and not m.delivered_late


def test_admin_sms_log_shows_both_times_and_late_flag(device, plan, staff_client, superadmin):
    order = _order(plan, minutes_ago=30)
    _post(device, [_sms(order.amount_unique, timezone.now() - timedelta(minutes=20))])
    row = staff_client(superadmin).get("/api/v1/admin/sms-log/").data["results"][0]
    assert row["delivered_late"] is True and row["uploaded_at"] > row["received_at"]
