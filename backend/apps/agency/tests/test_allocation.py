"""v1.35.1 invoices ↔ ledger (apps/agency/allocation.py): a manual «ثبت پرداخت» settles chosen invoices
(or oldest first, partial allowed), «کاهش بدهی» can settle invoices, «افزایش بدهی» never does,
«تسویه خارج از سیستم» keeps the charge and the balance, voiding a source re-opens what it settled,
unpaid invoices never exceed the ledger debt, and the reconcile command (mostafawire case)."""
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from apps.agency import allocation, billing, ledger
from apps.agency.models import AgencyInvoice, AgencyInvoiceAllocation, LedgerEntry
from apps.agency.tests.test_group_managers import M, make_manager, manager_client, pg, staff_client  # noqa: F401
from apps.agency.tests.test_invoices import quiet  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
L = "/api/v1/admin/agency/ledger/"


def charge(admin, amount):
    """A money charge → one invoice (oldest first = creation order)."""
    e = ledger.add_entry(admin, "manual_charge", amount, ledger.today(), by="t")
    return AgencyInvoice.objects.get(ledger_entry=e)


def post_entry(c, admin, **body):
    return c.post(f"{L}{admin}/entries/", {"date": str(ledger.today()), **body}, format="json")


def inv(i):
    return AgencyInvoice.objects.get(pk=i.pk)


def test_manual_payment_oldest_first_and_partial(pg):  # noqa: F811
    boss = staff_client(superadmin=True)
    a, b, c = charge("g1-a", 100000), charge("g1-a", 200000), charge("g1-a", 50000)
    r = post_entry(boss, "g1-a", kind="payment", amount="250000", method="card")   # default: oldest first
    assert r.status_code == 201, r.content
    assert inv(a).status == "paid" and inv(a).settled_via == "manual"
    assert inv(b).status == "unpaid" and inv(b).paid_amount == Decimal("150000")
    assert allocation.remaining(inv(b)) == Decimal("50000") and inv(c).paid_amount == 0
    pay = LedgerEntry.objects.get(kind="payment")
    assert [s["invoice"] for s in next(e for e in r.json()["entries"] if e["id"] == pay.id)["settles"]] == [a.number, b.number]
    d = boss.get("/api/v1/admin/agency/invoices/", {"admin": "g1-a", "status": "all"}).json()
    assert Decimal(str(d["unpaid_total"])) == Decimal("100000") == ledger.balances()["g1-a"]
    row = next(x for x in d["results"] if x["id"] == b.id)
    assert row["partial"] and Decimal(str(row["remaining"])) == Decimal("50000") and d["mismatch"] is None


def test_manual_payment_settles_the_chosen_invoices(pg):  # noqa: F811
    boss = staff_client(superadmin=True)
    a, b, c = charge("g1-a", 100000), charge("g1-a", 200000), charge("g1-a", 50000)
    r = post_entry(boss, "g1-a", kind="payment", amount="250000", method="cash", settle="selected",
                   invoice_ids=[c.id, b.id])
    assert r.status_code == 201, r.content
    assert inv(c).status == "paid" and inv(b).status == "paid" and inv(a).status == "unpaid" and inv(a).paid_amount == 0
    # another admin's invoice cannot be chosen; nothing is written then
    other = charge("g2-owner", 10000)
    r = post_entry(boss, "g1-a", kind="payment", amount="10000", method="cash", settle="selected", invoice_ids=[other.id])
    assert r.status_code == 400 and LedgerEntry.objects.filter(kind="payment").count() == 1


def test_adjustment_decrease_settles_increase_never_touches(pg):  # noqa: F811
    boss = staff_client(superadmin=True)
    a, b = charge("g1-a", 100000), charge("g1-a", 70000)
    assert post_entry(boss, "g1-a", kind="adjustment", direction="increase", amount="40000").status_code == 201
    assert inv(a).paid_amount == 0 and inv(b).paid_amount == 0
    r = post_entry(boss, "g1-a", kind="adjustment", direction="decrease", amount="70000", settle="selected", invoice_ids=[b.id])
    assert r.status_code == 201, r.content
    assert inv(b).status == "paid" and inv(b).settled_via == "adjustment" and inv(a).status == "unpaid"
    # an increase may not settle anything
    assert post_entry(boss, "g1-a", kind="adjustment", direction="increase", amount="1000",
                      settle="selected", invoice_ids=[a.id]).status_code == 400
    # settle "none": only the invariant (balance 140,000 ≥ unpaid 100,000 → nothing allocated)
    assert post_entry(boss, "g1-a", kind="adjustment", direction="decrease", amount="40000", settle="none").status_code == 201
    assert inv(a).paid_amount == 0


def test_outside_settlement_keeps_charge_and_balance(pg):  # noqa: F811
    boss = staff_client(superadmin=True)
    a = charge("g1-a", 300000)
    r = boss.post(f"/api/v1/admin/agency/invoices/{a.id}/settle-outside/", {"note": "paid in Mehr"}, format="json")
    assert r.status_code == 200, r.content
    a = inv(a)
    assert a.status == "paid" and a.settled_via == "outside" and a.paid_amount == Decimal("300000")
    assert not a.ledger_entry.voided and ledger.balances()["g1-a"] == Decimal("300000")
    assert not LedgerEntry.objects.filter(kind__in=("payment", "adjustment")).exists()
    # not offered again as "previous balance"
    assert billing.settlement_quote("g1-a")["amount"] == 0
    assert boss.post(f"/api/v1/admin/agency/invoices/{a.id}/settle-outside/", {}, format="json").status_code == 409
    clerk = staff_client(["agency.view"], name="clerk")
    b = charge("g1-a", 1000)
    assert clerk.post(f"/api/v1/admin/agency/invoices/{b.id}/settle-outside/", {}, format="json").status_code == 403
    # void still removes the charge too
    assert boss.post(f"/api/v1/admin/agency/invoices/{b.id}/void/", {"reason": "mistake"}, format="json").status_code == 200
    assert inv(b).status == "voided" and inv(b).ledger_entry.voided


def test_invariant_credit_before_the_charge_and_void_reopens(pg):  # noqa: F811
    boss = staff_client(superadmin=True)
    # mostafawire flow on the new code: charge, decrease, payment BEFORE the second charge, charge
    a = charge("g1-a", 3000000)
    post_entry(boss, "g1-a", kind="adjustment", direction="decrease", amount="3000000")
    post_entry(boss, "g1-a", kind="payment", amount="2000000", method="card")
    b = charge("g1-a", 2000000)
    assert ledger.balances()["g1-a"] == 0
    assert inv(a).status == "paid" and inv(a).settled_via == "adjustment"
    assert inv(b).status == "paid" and inv(b).settled_via == "manual"
    assert allocation.open_remaining("g1-a") == 0
    # voiding the payment re-opens the invoice it settled
    pay = LedgerEntry.objects.get(kind="payment", admin_username="g1-a")
    r = boss.post(f"{L}entries/{pay.id}/void/", {"reason": "bounced"}, format="json")
    assert r.status_code == 200, r.content
    assert inv(b).status == "unpaid" and inv(b).paid_amount == 0
    assert allocation.open_remaining("g1-a") <= max(Decimal(0), ledger.balances()["g1-a"])


def test_reconcile_command_preview_then_apply(pg):  # noqa: F811
    """Old data (before v1.35.1): invoices left unpaid although the ledger is at 0."""
    a = charge("g1-a", 3000000)
    LedgerEntry.objects.create(admin_username="g1-a", kind="adjustment", amount=Decimal("-3000000"), date=ledger.today())
    LedgerEntry.objects.create(admin_username="g1-a", kind="payment", amount=Decimal("2000000"), date=ledger.today(), method="card")
    e = LedgerEntry.objects.create(admin_username="g1-a", kind="manual_charge", amount=Decimal("2000000"), date=ledger.today())
    b = AgencyInvoice.objects.create(admin_username="g1-a", kind="manual_charge", amount=Decimal("2000000"), ledger_entry=e)
    assert allocation.mismatch("g1-a")["diff"] == Decimal("5000000")
    out = StringIO()
    call_command("reconcile_agency_invoices", stdout=out)
    text = out.getvalue()
    assert "g1-a: balance 0 · open invoices 5,000,000 · MISMATCH" in text and "preview" in text
    assert not AgencyInvoiceAllocation.objects.exists() and inv(a).status == "unpaid"
    call_command("reconcile_agency_invoices", "--apply", stdout=StringIO())
    assert inv(a).status == "paid" and inv(a).settled_via == "adjustment"
    assert inv(b).status == "paid" and inv(b).settled_via == "manual"
    assert allocation.mismatch("g1-a") is None
    out = StringIO()
    call_command("reconcile_agency_invoices", stdout=out)
    assert "0 admin(s)" in out.getvalue()


def test_manager_pays_the_rest_of_a_partly_paid_invoice(pg, quiet):  # noqa: F811
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    a = charge("g1-a", 100000)
    post_entry(boss, "g1-a", kind="payment", amount="30000", method="cash")
    mc = manager_client()
    row = next(x for x in mc.get(M + "invoices/").json()["results"] if x["id"] == a.id)
    assert Decimal(str(row["remaining"])) == Decimal("70000") and row["partial"]
    p = mc.post(M + "payments/", {"invoice_ids": [a.id]}, format="json")
    assert p.status_code == 201 and Decimal(str(p.json()["amount"])) == Decimal("70000")
    assert boss.post(f"/api/v1/admin/agency/payments/{p.json()['id']}/approve/", {}, format="json").status_code == 200
    a = inv(a)
    assert a.status == "paid" and a.settled_via == "mixed" and a.paid_amount == Decimal("100000")
    assert ledger.balances()["g1-a"] == 0
