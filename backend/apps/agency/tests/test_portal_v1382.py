"""v1.38.2 /agency/ portal: «کل بدهی» + «پرداخت کل بدهی» (one payment, 409 when the total changed) and «پرداخت انتخابی»
for direct admins, the invoice source label, paged notices (bell + page, mark one), and Web Push for resellers."""
from decimal import Decimal

import pytest

from apps.agency import billing, ledger
from apps.agency.models import AgencyInvoice, AgencyNotice, AgencyPayment, LedgerEntry, VolumeRequest
from apps.agency.tests.test_group_managers import GB, M, make_manager, manager_client, pg, staff_client  # noqa: F401
from apps.agency.tests.test_invoices import quiet, reseller  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
P = "/api/v1/agency/portal/"


def D(v):
    return Decimal(str(v))


def charge(admin, amount):
    e = ledger.add_entry(admin, "manual_charge", amount, ledger.today(), by="t")
    return AgencyInvoice.objects.get(ledger_entry=e)


def test_direct_admin_pays_the_whole_debt_in_one_payment(pg, quiet):  # noqa: F811
    LedgerEntry.objects.create(admin_username="g1-a", kind="manual_charge", amount=Decimal(40000), date=ledger.today())  # old
    a, b = charge("g1-a", 100000), charge("g1-a", 50000)
    c = reseller("g1-a")
    d = c.get(P + "debt/").json()
    assert D(d["total"]) == D(190000) == D(d["payable"]) and d["open_payment"] is None
    assert [i["type"] for i in d["admins"][0]["items"]] == ["invoice", "invoice", "old"]
    # a stale total is refused with the new amount — nothing is created
    r = c.post(P + "payments/all/", {"expected_total": "150000"}, format="json")
    assert r.status_code == 409 and r.json()["reason"] == "total_changed" and D(r.json()["total"]) == D(190000)
    assert not AgencyPayment.objects.exists()
    r = c.post(P + "payments/all/", {"expected_total": "190000"}, format="json")
    assert r.status_code == 201, r.content
    p = AgencyPayment.objects.get()
    assert p.payer_kind == "admin" and p.payer_username == "g1-a" and p.amount == D(190000) and p.items.count() == 3
    assert p.amount_unique > p.amount                                      # ONE unique amount for everything
    assert AgencyInvoice.objects.filter(admin_username="g1-a", kind="settlement").count() == 1
    assert c.get(P + "debt/").json()["open_payment"]["id"] == p.id


def test_selected_invoices_and_old_balance(pg, quiet):  # noqa: F811
    LedgerEntry.objects.create(admin_username="g1-a", kind="manual_charge", amount=Decimal(30000), date=ledger.today())
    a, b = charge("g1-a", 100000), charge("g1-a", 50000)
    c = reseller("g1-a")
    s = c.post(P + "invoices/settlement/", {}, format="json")
    assert s.status_code == 201 and s.json()["kind"] == "settlement" and D(s.json()["amount"]) == D(30000)
    r = c.post(P + "payments/", {"invoice_ids": [a.id, s.json()["id"]]}, format="json")
    assert r.status_code == 201, r.content
    assert D(r.json()["amount"]) == D(130000)
    # per-invoice «پرداخت» still works (one id); someone else's account → 403
    assert c.post(P + "payments/", {"invoice_id": b.id}, format="json").status_code == 201
    other = charge("g2-owner", 10000)
    assert c.post(P + "payments/", {"invoice_ids": [other.id]}, format="json").status_code == 403
    assert c.post(P + "invoices/settlement/", {"admin": "g2-owner"}, format="json").status_code == 403


def test_sub_admin_of_a_managed_group_is_read_only(pg, quiet):  # noqa: F811
    make_manager(staff_client(superadmin=True), pg)
    c = reseller("g1-a")
    assert c.get(P + "debt/").status_code == 403
    assert c.post(P + "payments/all/", {}, format="json").status_code == 403
    billing.notice(admin="g1-a", kind="invoice_issued", title="t", title_en="t")
    assert c.get(P + "notices/").json()["unread"] == 1                     # notices stay visible


def test_invoice_source_label(pg, quiet):  # noqa: F811
    boss = staff_client(superadmin=True)
    c = reseller("g1-a")
    c.post(P + "requests/", {"gb": 5}, format="json")
    rid = VolumeRequest.objects.get().id
    assert boss.post(f"/api/v1/admin/agency/approvals/{rid}/approve/", {}, format="json").status_code == 200
    boss.post("/api/v1/admin/agency/admins/g1-a/set-limit/", {"action": "add", "value_gb": 10}, format="json")
    LedgerEntry.objects.create(admin_username="g1-a", kind="manual_charge", amount=Decimal(1000), date=ledger.today())
    billing.issue_settlement("g1-a", by="t")
    rows = {r["kind"]: r["source"] for r in c.get(P + "invoices/").json()["results"]}
    assert rows == {"request": "admin_request", "quota_charge": "manual", "settlement": "settlement"}
    # volume a group manager added → «مدیر گروه»
    make_manager(boss, pg)
    assert manager_client().post(M + "admins/g1-owner/add-volume/", {"gb": 5}, format="json").status_code in (200, 201)
    vr = VolumeRequest.objects.filter(kind="add").first()
    assert boss.post(f"/api/v1/admin/agency/approvals/{vr.id}/approve/", {}, format="json").status_code == 200
    inv = AgencyInvoice.objects.get(volume_request=vr)
    assert billing.invoice_row(inv)["source"] == "manager"


def test_notices_paged_mark_one_and_reseller_push(pg, quiet, monkeypatch):  # noqa: F811
    from apps.notifications import webpush
    from apps.notifications.models import PushSubscription

    sent = []
    monkeypatch.setattr(webpush, "enabled", lambda: True)
    monkeypatch.setattr(webpush, "_queue", lambda ids, payload: sent.append((ids, payload)) or len(ids))
    c = reseller("g1-a")
    r = c.post(P + "push/subscribe/", {"subscription": {"endpoint": "https://push.example/abc", "keys": {"p256dh": "k", "auth": "a"}}},
               format="json")
    assert r.status_code == 200, r.content
    sub = PushSubscription.objects.get()
    assert sub.reseller == "g1-a" and sub.user_id is None and sub.staff_id is None
    assert c.get(P + "push/").json()["subscriptions"] == 1
    for i in range(25):
        billing.notice(admin="g1-a", kind="invoice_issued", title=f"n{i}", title_en=f"n{i}")
    assert sent and sent[-1][0] == [sub.id] and sent[-1][1]["url"] == "/agency/notifications"
    p2 = c.get(P + "notices/?page=2").json()
    assert p2["count"] == 25 and p2["pages"] == 2 and len(p2["results"]) == 5 and p2["unread"] == 25
    one = AgencyNotice.objects.filter(admin_username="g1-a").first()
    assert c.post(P + "notices/", {"id": one.id}, format="json").json()["unread"] == 24
    assert c.post(P + "notices/", {"read": True}, format="json").json()["unread"] == 0
    assert c.post(P + "push/unsubscribe/", {"endpoint": "https://push.example/abc"}, format="json").status_code == 200
    assert not PushSubscription.objects.exists()
