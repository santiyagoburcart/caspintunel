"""Rounded-amount auto-approve (payments_sms/rounded.py): a deposit slightly BELOW exactly one
open invoice is approved only with evidence (receipt / known payer card); everything else
stays in the review queue as before. Also the «لغو تأیید» undo and the Accounting figures."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.base import ContentFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.common.models import AuditLog
from apps.orders.models import OrderStatus
from apps.payments_sms.models import (
    BluStatus,
    BluTransaction,
    Payment,
    PaymentMethod,
    PaymentStatus,
    SmsAppDevice,
    SmsMessage,
    SmsSource,
)
from apps.payments_sms.tests.test_blu import INVOICE, env, item, make_order, post, staff_client  # noqa: F401
from apps.settings_app.utils import set_setting

pytestmark = pytest.mark.django_db(transaction=True)

ROUNDED = 174000            # INVOICE 175,662 − 1,662 (≤ max(2,000, 1 %))


def receipt(order):
    p = Payment(order=order, method=PaymentMethod.CARD_MANUAL, amount=order.amount_unique, status=PaymentStatus.PENDING)
    p.receipt_image.save("r.jpg", ContentFile(b"\xff\xd8fake"), save=False)
    p.save()
    return p


def revenue(c):
    return c.get("/api/v1/admin/accounting/?period=monthly").json()


def test_one_candidate_with_receipt_is_approved_and_flagged(env):  # noqa: F811
    o = make_order()
    receipt(o)
    c = staff_client("super", "boss")
    before = Decimal(revenue(c)["revenue"])
    post([item(ROUNDED, id="R1")])
    o.refresh_from_db()
    assert o.status in (OrderStatus.PAID, OrderStatus.COMPLETED)
    p = Payment.objects.get(order=o)
    assert p.status == PaymentStatus.APPROVED and p.method == PaymentMethod.BLU_AUTO
    assert p.auto_rule == "rounded" and p.amount == ROUNDED and p.shortfall == INVOICE - ROUNDED
    r = p.auto_reason
    assert r["applied"] is True and r["candidates"] == 1 and r["receipt"] is True and r["window"] is True
    assert Decimal(r["tolerance"]) == 2000
    tx = BluTransaction.objects.get(bank_id="R1")
    assert tx.status == BluStatus.MATCHED and tx.matched_payment_id == p.id and "rounded amount" in tx.match_note
    assert any(e == "rounded_approved" for e, _ in env["events"])
    assert any("مبلغ گرد شده" in text for text, _ in env["alerts"])
    assert AuditLog.objects.filter(action="payment.rounded_auto_confirmed", target_id=p.id).exists()
    # Accounting counts what was paid, and shows the shortfall
    acc = revenue(c)
    assert Decimal(acc["revenue"]) - before == ROUNDED
    assert acc["rounded"] == {"count": 1, "shortfall": str(INVOICE - ROUNDED), "paid": str(ROUNDED)}
    d = c.get(f"/api/v1/admin/transactions/{p.id}/").json()
    assert d["auto_rule"] == "rounded" and Decimal(d["shortfall"]) == INVOICE - ROUNDED


def test_two_candidates_go_to_the_queue():
    a = make_order(INVOICE, "a")
    b = make_order(175000, "b")
    receipt(a)
    post([item(174500, id="TWO")])
    for o in (a, b):
        o.refresh_from_db()
        assert o.status == OrderStatus.PENDING_PAYMENT
    assert not Payment.objects.filter(status=PaymentStatus.APPROVED).exists()
    flagged = Payment.objects.get(order=BluTransaction.objects.get(bank_id="TWO").matched_order)
    assert flagged.status == PaymentStatus.PENDING
    assert flagged.auto_reason["why_not"] == "multiple_orders" and flagged.auto_reason["candidates"] == 2


def test_no_receipt_and_a_new_card_go_to_the_queue():
    o = make_order()
    post([item(ROUNDED, id="NOEV")])
    o.refresh_from_db()
    assert o.status == OrderStatus.PENDING_PAYMENT
    p = Payment.objects.get(order=o)
    assert p.status == PaymentStatus.PENDING and p.method == PaymentMethod.BLU_MISMATCH and p.auto_rule == ""
    assert p.auto_reason["why_not"] == "no_evidence" and p.auto_reason["card_known"] is False
    assert "rounded rule not applied" in BluTransaction.objects.get(bank_id="NOEV").match_note
    rows = staff_client("super", "boss").get("/api/v1/admin/payments/pending/").json()["results"]
    assert rows[0]["auto_reason"]["why_not"] == "no_evidence" and rows[0]["sms_mismatch"]["kind"] == "less"


def test_a_card_the_customer_paid_from_before_is_evidence():
    old = make_order(150001, "k")
    post([item(150001, id="OLD", payer_card_last4="7777", payer_card="603799******7777")])
    assert Payment.objects.get(order=old).status == PaymentStatus.APPROVED
    o = make_order(INVOICE, "k2")
    o.user = old.user
    o.save(update_fields=["user"])
    post([item(ROUNDED, id="CARD", payer_card_last4="7777", payer_card="603799******7777")])
    p = Payment.objects.get(order=o)
    assert p.status == PaymentStatus.APPROVED and p.auto_reason["card_known"] is True
    assert p.auto_reason["receipt"] is False and p.auto_reason["card_last4"] == "7777"


def test_over_payment_is_not_this_rule():
    o = make_order()
    receipt(o)
    post([item(INVOICE + 1000, id="MORE")])
    p = Payment.objects.get(order=o)
    assert p.status == PaymentStatus.PENDING and p.auto_rule == "" and not p.auto_reason
    o.refresh_from_db()
    assert o.status == OrderStatus.PENDING_PAYMENT


def test_shortfall_over_the_tolerance_is_not_approved():
    o = make_order()
    receipt(o)
    post([item(INVOICE - 2001, id="FAR")])                 # 1 % of 175,662 = 1,756 < 2,000 < 2,001
    assert Payment.objects.get(order=o).status == PaymentStatus.PENDING


def test_exact_amount_is_unaffected():
    o = make_order()
    receipt(o)
    post([item(INVOICE, id="EXACT")])
    p = Payment.objects.get(order=o)
    assert p.status == PaymentStatus.APPROVED and p.auto_rule == "" and p.amount == INVOICE and p.shortfall is None


def test_setting_off_keeps_it_in_the_queue():
    set_setting("rounded_auto_enabled", "false", "bool")
    o = make_order()
    receipt(o)
    post([item(ROUNDED, id="OFF")])
    assert Payment.objects.get(order=o).status == PaymentStatus.PENDING


def test_bigger_tolerance_settings_apply():
    set_setting("rounded_max_toman", 0, "int")
    set_setting("rounded_max_percent", "3", "str")          # 3 % of 175,662 = 5,269
    o = make_order()
    receipt(o)
    post([item(INVOICE - 5000, id="PCT")])
    p = Payment.objects.get(order=o)
    assert p.status == PaymentStatus.APPROVED and Decimal(p.auto_reason["tolerance"]) == 5269


def _sms_client():
    SmsSource.objects.create(phone_number="+989999987641", description="blu")
    device = SmsAppDevice.objects.create(name="iPhone", is_active=True)
    c = APIClient(); c.credentials(HTTP_X_DEVICE_TOKEN=device.api_token)
    return c


def _sms(c, toman):
    text = f"بلو\nواریز پول\nپویا عزیز،{toman * 10:,} ریال به حساب شخصی شما نشست.\nموجودی: 1 ریال"
    return c.post("/api/v1/payments/sms/inbound/", {"text": text, "sender": "+989999987641"}, format="json").data


def test_sms_same_rule_with_receipt():
    c = _sms_client()
    o = make_order()
    receipt(o)
    r = _sms(c, ROUNDED)
    assert r["matched"] is True and r["rounded"] is True
    p = Payment.objects.get(order=o)
    assert p.method == PaymentMethod.SMS_AUTO and p.auto_rule == "rounded" and p.amount == ROUNDED
    msg = SmsMessage.objects.get(pk=r["message_id"])
    assert msg.matched_order_id == o.id and "rounded amount" in msg.note
    # the same deposit seen again via Blu is never approved twice
    post([item(ROUNDED, id="SAME")])
    tx = BluTransaction.objects.get(bank_id="SAME")
    assert tx.status == BluStatus.UNMATCHED and Payment.objects.filter(status=PaymentStatus.APPROVED).count() == 1


def test_sms_without_evidence_is_flagged_like_today():
    c = _sms_client()
    o = make_order()
    r = _sms(c, ROUNDED)
    assert r["matched"] is False and r["mismatch"] == "less"
    p = Payment.objects.get(order=o)
    assert p.method == PaymentMethod.SMS_MISMATCH and p.auto_reason["why_not"] == "no_evidence"


def test_receipt_uploaded_after_the_deposit_approves_it():
    from apps.payments_sms.services import submit_receipt

    o = make_order()
    post([item(ROUNDED, id="LATE")])
    assert Payment.objects.get(order=o).status == PaymentStatus.PENDING
    submit_receipt(order=o, image=ContentFile(b"\xff\xd8x", name="x.jpg"), user=o.user)
    p = Payment.objects.get(order=o)
    assert p.status == PaymentStatus.APPROVED and p.auto_rule == "rounded" and p.auto_reason["receipt"] is True
    assert BluTransaction.objects.get(bank_id="LATE").status == BluStatus.MATCHED


def test_undo_voids_it_and_returns_the_deposit():
    o = make_order()
    receipt(o)
    post([item(ROUNDED, id="UNDO")])
    p = Payment.objects.get(order=o)
    c = staff_client("super", "boss")
    rev = Decimal(revenue(c)["revenue"])
    other = staff_client(["payment.view", "payment.approve"], "clerk")
    assert other.post(f"/api/v1/admin/transactions/{p.id}/undo-rounded/", {}, format="json").status_code == 403
    r = c.post(f"/api/v1/admin/transactions/{p.id}/undo-rounded/", {"reason": "wrong customer"}, format="json")
    assert r.status_code == 200, r.content
    assert r.json()["service_result"] in ("kept", "no_service") and "message_fa" in r.json()
    p.refresh_from_db()
    assert p.voided_at and p.void_service_action == "keep" and p.void_reason.startswith("لغو تأیید خودکار")
    o.refresh_from_db()
    assert o.status in (OrderStatus.PAID, OrderStatus.COMPLETED)            # service kept
    tx = BluTransaction.objects.get(bank_id="UNDO")
    assert tx.status == BluStatus.UNMATCHED and tx.matched_payment_id is None and "undone" in tx.match_note
    assert Decimal(revenue(c)["revenue"]) == rev - ROUNDED
    assert AuditLog.objects.filter(action="payment.rounded_undone", target_id=p.id).exists()
    # an exact approval cannot be "undone" this way
    o2 = make_order(160001, "x")
    post([item(160001, id="EX2")])
    p2 = Payment.objects.get(order=o2)
    assert c.post(f"/api/v1/admin/transactions/{p2.id}/undo-rounded/", {}, format="json").status_code == 400
    # restore puts the deposit back on the payment
    assert c.post(f"/api/v1/admin/transactions/{p.id}/restore/").status_code == 200
    tx.refresh_from_db()
    assert tx.status == BluStatus.MATCHED and tx.matched_payment_id == p.id


def test_deposit_after_the_window_is_not_approved():
    o = make_order()
    receipt(o)
    post([item(ROUNDED, id="OLDW", at=timezone.now() - timedelta(hours=2))])
    assert Payment.objects.get(order=o).status == PaymentStatus.PENDING
