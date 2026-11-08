"""v1.44.1 rounded-amount rule widened (payments_sms/rounded.py): ± rounded_max_toman (default 2,000 T) below AND above,
inside the order's window, exactly ONE open order / agency payment fits, the deposit not already used. Over-payments need
no evidence; below still needs a receipt or a known card. Flag «کمتر X» / «بیشتر X», Accounting splits less / more,
«لغو تأیید» works, renewals and manual invoices are covered, and the queue gets the Blu deposit pre-filled."""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.orders.models import Order, OrderStatus, OrderType
from apps.orders.services import create_order
from apps.orders.tests.test_renew_same_account import _service, panel, plans, user  # noqa: F401 — fixtures
from apps.payments_sms.models import BluStatus, BluTransaction, Payment, PaymentStatus, SmsAppDevice, SmsSource
from apps.payments_sms.rounded import diff_label
from apps.payments_sms.tests.test_blu import INVOICE, env, item, make_order, post, staff_client  # noqa: F401
from apps.payments_sms.tests.test_rounded import receipt

pytestmark = pytest.mark.django_db(transaction=True)


def _approved(o, paid):
    o.refresh_from_db()
    p = Payment.objects.get(order=o)
    assert o.status in (OrderStatus.PAID, OrderStatus.COMPLETED), o.status
    assert p.status == PaymentStatus.APPROVED and p.auto_rule == "rounded" and p.amount == paid
    assert p.shortfall == Decimal(o.amount_unique) - paid
    return p


def _queued(o):
    o.refresh_from_db()
    assert o.status == OrderStatus.PENDING_PAYMENT
    assert not Payment.objects.filter(order=o, status=PaymentStatus.APPROVED).exists()


def test_plus_65_is_approved_without_any_evidence(env):  # noqa: F811
    o = make_order()
    post([item(INVOICE + 65, id="P65")])
    p = _approved(o, INVOICE + 65)
    r = p.auto_reason
    assert r["direction"] == "more" and r["diff"] == "65" and r["evidence_required"] is False and r["applied"] is True
    assert r["receipt"] is False and Decimal(r["tolerance"]) == 2000
    assert any("مبلغ گرد شده (بیشتر 65)" in text for text, _ in env["alerts"])
    assert any(e == "rounded_approved" and kw.get("direction") == "more" for e, kw in env["events"])
    assert "over 65 T" in BluTransaction.objects.get(bank_id="P65").match_note


def test_plus_1000_counts_what_was_paid_and_shows_more_in_accounting():
    o = make_order()
    c = staff_client("super", "acc-boss")
    before = Decimal(c.get("/api/v1/admin/accounting/?period=monthly").json()["revenue"])
    post([item(INVOICE + 1000, id="P1000")])
    p = _approved(o, INVOICE + 1000)
    acc = c.get("/api/v1/admin/accounting/?period=monthly").json()
    assert Decimal(acc["revenue"]) - before == INVOICE + 1000
    assert acc["rounded"]["over"] == "1000" and acc["rounded"]["more_count"] == 1 and acc["rounded"]["shortfall"] == "0"
    d = c.get(f"/api/v1/admin/transactions/{p.id}/").json()
    assert d["auto_rule"] == "rounded" and Decimal(d["shortfall"]) == -1000
    assert diff_label(d["shortfall"]) == "بیشتر 1,000" and diff_label(d["shortfall"], "en") == "more 1,000"


def test_minus_1000_needs_evidence_and_is_flagged_less():
    bare = make_order()
    post([item(INVOICE - 1000, id="M1000-bare")])
    _queued(bare)                                                   # below without receipt / known card → queue
    assert Payment.objects.get(order=bare).auto_reason["why_not"] == "no_evidence"
    Order.objects.filter(pk=bare.pk).update(status=OrderStatus.EXPIRED, amount_unique_lock=None)
    o = make_order(INVOICE + 7, "c2")
    receipt(o)
    post([item(INVOICE + 7 - 1000, id="M1000")])
    p = _approved(o, INVOICE + 7 - 1000)
    assert p.auto_reason["direction"] == "less" and diff_label(p.shortfall) == "کمتر 1,000"


def test_minus_2000_is_the_edge_and_still_approved():
    o = make_order()
    receipt(o)
    post([item(INVOICE - 2000, id="M2000")])
    _approved(o, INVOICE - 2000)


def test_plus_2500_goes_to_the_queue():
    o = make_order()
    post([item(INVOICE + 2500, id="P2500")])
    _queued(o)
    p = Payment.objects.get(order=o)                                 # «مبلغ نامطابق — بیشتر» for staff
    assert p.status == PaymentStatus.PENDING and p.auto_rule == ""
    assert BluTransaction.objects.get(bank_id="P2500").status == BluStatus.UNMATCHED


def test_two_candidates_one_below_one_above_go_to_the_queue():
    a = make_order(INVOICE, "a1")
    b = make_order(INVOICE + 1500, "b1")
    post([item(INVOICE + 700, id="TWO")])                             # +700 over a, −800 under b
    _queued(a)
    _queued(b)
    tx = BluTransaction.objects.get(bank_id="TWO")
    assert tx.status == BluStatus.UNMATCHED and "2+ orders fit" in tx.match_note


def test_a_renewal_is_paid_by_a_rounded_deposit(user, panel, plans):  # noqa: F811
    a, _, _ = plans
    svc = _service(user, panel, a)
    o = create_order(user=user, plan_id=a.id, order_type=OrderType.RENEW, service_id=svc.id)
    Order.objects.filter(pk=o.pk).update(amount_unique=Decimal(INVOICE), amount_unique_lock=Decimal(INVOICE))
    post([item(INVOICE + 1000, id="RENEW")])
    p = _approved(o, INVOICE + 1000)
    assert p.order.type == OrderType.RENEW


def _sms(toman):
    if not SmsSource.objects.exists():
        SmsSource.objects.create(phone_number="+989999987641", description="blu")
    device = SmsAppDevice.objects.first() or SmsAppDevice.objects.create(name="iPhone", is_active=True)
    c = APIClient(); c.credentials(HTTP_X_DEVICE_TOKEN=device.api_token)
    text = f"بلو\nواریز پول\nپویا عزیز،{toman * 10:,} ریال به حساب شخصی شما نشست.\nموجودی: 1 ریال"
    return c.post("/api/v1/payments/sms/inbound/", {"text": text, "sender": "+989999987641"}, format="json").data


def test_sms_over_payment_is_approved_too():
    o = make_order()
    res = _sms(INVOICE + 1000)
    assert res["matched"] is True and res.get("rounded") is True
    p = _approved(o, INVOICE + 1000)
    assert p.sms_message_id and p.auto_reason["source"] == "sms"


def test_the_same_transfer_seen_twice_never_pays_a_neighbour():
    """Blu pays order A exactly; the iPhone SMS of that SAME transfer arrives later — order B, 1,000 T below, must not be
    approved with it (over-payment, no evidence needed — so only the "already used" guard stops it)."""
    a = make_order(INVOICE, "a2")
    b = make_order(INVOICE - 1000, "b2")
    post([item(INVOICE, id="EXACT-A")])
    a.refresh_from_db()
    assert a.status in (OrderStatus.PAID, OrderStatus.COMPLETED)
    res = _sms(INVOICE)
    assert not res.get("rounded")
    _queued(b)


def test_undo_an_over_payment_hands_the_deposit_back():
    o = make_order()
    post([item(INVOICE + 1000, id="UNDO")])
    p = _approved(o, INVOICE + 1000)
    r = staff_client("super", "undo-boss").post(f"/api/v1/admin/transactions/{p.id}/undo-rounded/", {"reason": "x"},
                                                format="json")
    assert r.status_code == 200, r.content
    p.refresh_from_db()
    assert p.voided_at is not None
    tx = BluTransaction.objects.get(bank_id="UNDO")
    assert tx.status == BluStatus.UNMATCHED and tx.matched_payment_id is None


def test_the_queue_prefills_receipt_amount_and_tracking_from_a_blu_deposit():
    o = make_order()
    receipt(o)                                                       # a receipt waiting for review
    post([item(INVOICE + 2500, id="PREFILL")])                       # too far: linked to the order, not approved
    c = staff_client("super", "queue-boss")
    row = next(r for r in c.get("/api/v1/admin/payments/pending/").json()["results"] if r["order_id"] == o.id)
    tx = BluTransaction.objects.get(bank_id="PREFILL")
    assert row["blu_prefill"]["id"] == tx.id and Decimal(str(row["blu_prefill"]["amount"])) == INVOICE + 2500
    assert row["blu_prefill"]["tracking"] == "249042"


def test_no_prefill_without_a_matching_deposit():
    o = make_order()
    receipt(o)
    row = next(r for r in staff_client("super", "q2").get("/api/v1/admin/payments/pending/").json()["results"]
               if r["order_id"] == o.id)
    assert row["blu_prefill"] is None
