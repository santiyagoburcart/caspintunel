"""v1.35.2 «کل بدهی گروه»: one live total (open invoices + old balances) that matches the ledger, «پرداخت کل بدهی»
= settlement invoices + ONE payment for exactly that total (409 + new amount if it changed), the read-only
breakdown, and the same total for staff (Agency → Groups)."""
from decimal import Decimal

import pytest

from apps.agency import ledger
from apps.agency.models import AgencyInvoice, AgencyPayment, LedgerEntry
from apps.agency.tests.test_group_managers import M, make_manager, manager_client, pg, staff_client  # noqa: F401
from apps.agency.tests.test_invoices import quiet  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def old_debt(admin, amount):
    LedgerEntry.objects.create(admin_username=admin, kind="manual_charge", amount=Decimal(amount), date=ledger.today())


def charge(admin, amount):
    e = ledger.add_entry(admin, "manual_charge", amount, ledger.today(), by="t")
    return AgencyInvoice.objects.get(ledger_entry=e)


def D(v):
    return Decimal(str(v))


def setup(pg):  # noqa: F811
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    old_debt("g1-owner", 90000)                    # from before invoices
    a = charge("g1-a", 100000)
    charge("g1-a", 50000)
    ledger.add_entry("g1-a", "payment", 30000, ledger.today(), method="cash")   # → a partly paid
    return boss, a


def test_total_matches_the_ledger_and_breakdown(pg, quiet):  # noqa: F811
    boss, a = setup(pg)
    d = manager_client().get(M + "debt/").json()
    assert D(d["total"]) == D(90000 + 70000 + 50000) == D(d["ledger_debt"]) == D(d["payable"])
    rows = {r["admin"]: r for r in d["admins"]}
    assert [i["type"] for i in rows["g1-owner"]["items"]] == ["old"] and D(rows["g1-owner"]["total"]) == D(90000)
    inv = rows["g1-a"]["items"][0]
    assert inv["number"] == a.number and D(inv["amount"]) == D(70000) and inv["partial"]
    assert D(rows["g1-unl"]["total"]) == 0                     # zero-debt admins are in the data (hidden in the UI)
    # staff see the same number for the group
    s = boss.get(f"/api/v1/admin/agency/groups/{pg['g1'].id}/debt/").json()
    assert D(s["total"]) == D(d["total"])
    assert staff_client(["agency.view"], name="v").get(f"/api/v1/admin/agency/groups/{pg['g1'].id}/debt/").status_code == 403


def test_pay_all_bundles_everything_into_one_payment(pg, quiet):  # noqa: F811
    boss, a = setup(pg)
    mc = manager_client()
    r = mc.post(M + "payments/all/", {"expected_total": "210000"}, format="json")
    assert r.status_code == 201, r.content
    p = AgencyPayment.objects.get(pk=r.json()["id"])
    assert p.amount == Decimal("210000") and p.amount_unique >= p.amount and p.items.count() == 3
    assert AgencyInvoice.objects.filter(kind="settlement", admin_username="g1-owner", amount=Decimal("90000")).exists()
    # normal approval path → everything paid, ledger at zero, the total drops to 0
    assert boss.post(f"/api/v1/admin/agency/payments/{p.id}/approve/", {}, format="json").status_code == 200
    assert ledger.balances()["g1-a"] == 0 and ledger.balances()["g1-owner"] == 0
    assert D(mc.get(M + "debt/").json()["total"]) == 0
    assert mc.post(M + "payments/all/", {}, format="json").status_code == 409


def test_pay_all_refuses_a_changed_total(pg, quiet):  # noqa: F811
    setup(pg)
    mc = manager_client()
    charge("g1-a", 5000)                                      # changed after the page loaded
    r = mc.post(M + "payments/all/", {"expected_total": "210000"}, format="json")
    assert r.status_code == 409 and r.json()["reason"] == "total_changed" and D(r.json()["total"]) == D(215000)
    assert not AgencyPayment.objects.exists() and not AgencyInvoice.objects.filter(kind="settlement").exists()
    assert mc.post(M + "payments/all/", {"expected_total": "215000"}, format="json").status_code == 201


def test_pay_all_skips_direct_admins_and_new_settlement_after_paid(pg, quiet):  # noqa: F811
    boss, _ = setup(pg)
    old_debt("g2-owner", 40000)                               # not in the manager's groups
    mc = manager_client()
    p = mc.post(M + "payments/all/", {}, format="json").json()
    assert "g2-owner" not in p["admins"]
    boss.post(f"/api/v1/admin/agency/payments/{p['id']}/approve/", {}, format="json")
    # debt added later without an invoice gets a NEW settlement invoice through «پرداخت کل بدهی»
    ledger.add_entry("g1-owner", "adjustment", 12000, ledger.today(), direction="increase")
    d = mc.get(M + "debt/").json()
    assert D(d["total"]) == D(12000)
    assert mc.post(M + "payments/all/", {"expected_total": "12000"}, format="json").status_code == 201
    assert AgencyInvoice.objects.filter(kind="settlement", admin_username="g1-owner").count() == 2
