"""v1.42.2 Blu tab «اتصال»: any reference (order id, TX-, MI-, INV-/AP-), candidates, link to a paid target = link only
(no double count), link to an unpaid target = approve (short → confirm + shortfall), auto-link when a payment is approved
by another route (same reference, else same amount + time + payer name), backfill, unlink (Super Admin), Persian notes."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Staff
from apps.common.models import AuditLog
from apps.orders.models import OrderStatus
from apps.payments_sms import blu_link
from apps.payments_sms.blu_notes import note_fa
from apps.payments_sms.models import BluStatus, BluTransaction, Payment, PaymentMethod, PaymentStatus
from apps.payments_sms.services import approve_payment
from apps.payments_sms.tests.test_blu import env, make_order, staff_client  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
U = "/api/v1/admin/payments/blu-transactions/"


def deposit(toman, *, ref="", receipt="", name="بهرام آیرملو", at=None, n=[0]):
    n[0] += 1
    return BluTransaction.objects.create(
        bank_id=f"t-{n[0]}-{toman}-{ref}", amount_irr=int(toman) * 10, amount_toman=Decimal(toman),
        occurred_at=at or timezone.now() - timedelta(minutes=30), direction="بستانکار", payer_name=name,
        payer_card="603799******5440", payer_last4="5440", receipt=receipt, reference=ref,
        status=BluStatus.UNMATCHED, match_note=f"no pending order of exactly {int(toman):,} T at the deposit time")


def paid_by_receipt(amount=800000, name="mi1", user_name="بهرام آیرملو", ref=""):
    """An order approved by staff from a receipt (like a manual invoice / receipt approval)."""
    o = make_order(amount, name=name)
    o.user.name = user_name
    o.user.save()
    p = Payment.objects.create(order=o, method=PaymentMethod.CARD_MANUAL, amount=o.amount_unique,
                               status=PaymentStatus.PENDING, receipt_ref=ref)
    approve_payment(p.id)
    p.refresh_from_db()
    return o, p


def revenue(boss):
    return Decimal(str(boss.get("/api/v1/admin/accounting/").json()["revenue"]))


def test_link_to_an_already_paid_order_is_link_only_and_never_double_counted():
    o, p = paid_by_receipt(ref="")                          # no reference → nothing auto-links by reference
    BluTransaction.objects.all().delete()
    tx = deposit(800000, ref="130080897033", receipt="897033", name="someone else")
    boss = staff_client("super", "link-boss")
    before_rev, before_n = revenue(boss), Payment.objects.filter(status="approved").count()
    r = boss.post(f"{U}{tx.id}/attach/", {"ref": p.tx_number}, format="json")
    assert r.status_code == 200, r.content
    assert r.json()["result"] == "linked" and "متصل" in r.json()["message_fa"]
    tx.refresh_from_db(); p.refresh_from_db()
    assert tx.status == BluStatus.LINKED and tx.matched_payment_id == p.id and p.blu_transaction_id == tx.id
    assert Payment.objects.filter(status="approved").count() == before_n and revenue(boss) == before_rev
    assert p.method == PaymentMethod.CARD_MANUAL                # the payment itself is untouched
    blu = boss.get(f"/api/v1/admin/transactions/{p.id}/").json()["blu"]
    assert blu["linked"] and blu["reference"] == "130080897033" and blu["payer_card"].endswith("5440")
    assert AuditLog.objects.filter(action="blu.linked", detail__blu_transaction=tx.id).exists()


def test_link_to_an_unpaid_order_approves_it_and_a_short_deposit_needs_confirm():
    o = make_order(176195, name="sahar_x")
    tx = deposit(175000)
    boss = staff_client("super", "short-boss")
    r = boss.post(f"{U}{tx.id}/attach/", {"ref": f"#{o.id}"}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "needs_confirm" and r.json()["shortfall"] == "1195"
    assert "کسری 1,195 تومان" in r.json()["detail_fa"]
    r = boss.post(f"{U}{tx.id}/attach/", {"ref": str(o.id), "confirm": True}, format="json")
    assert r.status_code == 200 and r.json()["result"] == "approved" and r.json()["shortfall"] == "1195"
    o.refresh_from_db(); tx.refresh_from_db()
    p = Payment.objects.get(order=o)
    assert p.status == PaymentStatus.APPROVED and p.method == PaymentMethod.BLU_AUTO
    assert p.amount == Decimal("175000") and p.shortfall == Decimal("1195")
    assert o.status in (OrderStatus.PAID, OrderStatus.COMPLETED)
    assert tx.status == BluStatus.MATCHED and tx.matched_payment_id == p.id
    exact = make_order(250000, name="exact1")
    tx2 = deposit(250000)
    assert boss.post(f"{U}{tx2.id}/attach/", {"ref": str(exact.id)}, format="json").json()["result"] == "approved"


def test_auto_link_when_a_payment_with_the_same_reference_is_approved():
    tx = deposit(800000, ref="130080897033", receipt="897033")
    o, p = paid_by_receipt(ref="130080897033", user_name="")
    tx.refresh_from_db(); p.refresh_from_db()
    assert tx.status == BluStatus.LINKED and p.blu_transaction_id == tx.id and "same_reference" in tx.match_note
    assert note_fa(tx.match_note).startswith("به پرداخت موجود")


def test_auto_link_by_amount_time_and_name_only_when_unambiguous():
    tx = deposit(320000, name="مهدی جلائی")
    o, p = paid_by_receipt(320000, name="mahdi1", user_name="مهدی جلائی")
    tx.refresh_from_db()
    assert tx.status == BluStatus.LINKED and tx.matched_order_id == o.id
    deposit(410000, name="علی"); deposit(410000, name="علی")       # two equal deposits: never guessed
    o2, p2 = paid_by_receipt(410000, name="ali1", user_name="علی")
    assert not BluTransaction.objects.filter(matched_order=o2).exists()
    deposit(510000, name="رضا")                                   # another payer's name: not linked
    o3, _ = paid_by_receipt(510000, name="sara1", user_name="سارا")
    assert not BluTransaction.objects.filter(matched_order=o3).exists()


def test_backfill_links_existing_deposits_and_dry_run_changes_nothing():
    o, p = paid_by_receipt(ref="186545960754", user_name="")
    tx = deposit(800000, ref="186545960754", at=p.confirmed_at - timedelta(hours=1))   # arrived in the tab later
    assert blu_link.backfill(dry_run=True) == [{"blu": tx.id, "payment": p.tx_number}]
    tx.refresh_from_db()
    assert tx.status == BluStatus.UNMATCHED
    assert blu_link.backfill() == [{"blu": tx.id, "payment": p.tx_number}]
    tx.refresh_from_db()
    assert tx.status == BluStatus.LINKED
    assert blu_link.backfill() == []                                                    # idempotent


def test_unlink_is_super_admin_only_and_audited():
    o, p = paid_by_receipt(ref="")
    tx = deposit(800000, name="x y z")
    boss = staff_client("super", "unlink-boss")
    boss.post(f"{U}{tx.id}/attach/", {"ref": p.tx_number}, format="json")
    assert staff_client(["payment.approve", "payment.view"], "approver").post(f"{U}{tx.id}/unlink/").status_code == 403
    r = boss.post(f"{U}{tx.id}/unlink/")
    assert r.status_code == 200, r.content
    tx.refresh_from_db(); p.refresh_from_db()
    assert tx.status == BluStatus.UNMATCHED and tx.matched_payment_id is None and p.blu_transaction_id is None
    assert AuditLog.objects.filter(action="blu.unlinked", detail__payment=p.id).exists()
    # an approval made WITH a deposit is not "unlinked" (that is a void)
    o2 = make_order(250000, name="appr1")
    tx2 = deposit(250000)
    boss.post(f"{U}{tx2.id}/attach/", {"ref": str(o2.id)}, format="json")
    assert boss.post(f"{U}{tx2.id}/unlink/").status_code == 409


def test_references_and_candidates():
    o, p = paid_by_receipt(ref="")
    tx = deposit(800000, ref="999888777666", name="بهرام آیرملو")
    assert blu_link.resolve(p.tx_number).order.id == o.id
    assert blu_link.resolve(f"ORD-{o.id}").order.id == o.id
    with pytest.raises(blu_link.LinkError):
        blu_link.resolve("XYZ-1")
    from apps.agency.models import AgencyPayment

    ap = AgencyPayment.objects.create(payer_kind="admin", payer_username="res1", amount=Decimal("800000"),
                                      amount_unique=Decimal("800310"), status="approved",
                                      confirmed_at=timezone.now(), receipt_ref="",
                                      unique_expire_at=timezone.now() + timedelta(minutes=30))
    assert blu_link.resolve(ap.number).agency.id == ap.id
    other = make_order(700000, name="other1")
    rows = staff_client("super", "cand-boss").get(f"{U}{tx.id}/candidates/").json()["results"]
    keys = [r["key"] for r in rows]
    assert f"order:{o.id}" in keys and f"order:{other.id}" in keys and f"ap:{ap.id}" in keys
    top = rows[0]
    assert top["key"] == f"order:{o.id}" and "same_amount" in top["why"] and "payer_name" in top["why"]
    # link to the paid agency payment = link only
    tx2 = deposit(800310, name="")
    r = staff_client("super", "ap-boss").post(f"{U}{tx2.id}/attach/", {"ref": ap.number}, format="json")
    assert r.status_code == 200 and r.json()["result"] == "linked"
    ap.refresh_from_db()
    assert ap.blu_transaction_id == tx2.id


def test_match_notes_in_persian():
    assert note_fa("no pending order of exactly 800,000 T at the deposit time") == \
        "در زمان واریز سفارش در انتظاری با مبلغ دقیق 800,000 تومان وجود نداشت"
    assert "کمتر از فاکتور" in note_fa("amount mismatch — LESS than invoice, NOT approved, review by hand: deposit "
                                       "250,000 T, order #122 expects 252,100 T")
    assert note_fa("matched order #125 (176,195 T) — rounded amount — auto-approved: 1 order(s) fit, short 1,195 T "
                   "≤ 5,000 T").startswith("به سفارش #125 (176,195 تومان) وصل شد — مبلغ گرد شده")
    assert note_fa("something new") == "something new"
    tx = deposit(123000)
    row = staff_client("super", "fa-boss").get(U).json()["results"][0]
    assert row["id"] == tx.id and row["match_note_fa"].startswith("در زمان واریز")
