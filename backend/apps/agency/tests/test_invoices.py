"""v1.34 agency invoices, admin volume requests and agency payments (apps/agency/billing.py):
an invoice per charge type, missing price, request → approve → limit + invoice, paying by SMS /
Blu (exact), rounded amount, manual review, a group manager paying several invoices at once, no
collision with customer unique amounts, and separation from customer revenue."""
import secrets
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.base import ContentFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.agency import billing, ledger, portal
from apps.agency.models import (AgencyInvoice, AgencyNotice, AgencyPayment, LedgerEntry, PanelAdmin, ResellerSession,
                                VolumeRequest)
from apps.agency.tests.test_group_managers import GB, M, make_manager, manager_client, pg, staff_client  # noqa: F401
from apps.payments_sms.models import Payment, SmsAppDevice, SmsSource
from apps.payments_sms.tests.test_blu import item, post
from apps.settings_app.models import ValueType
from apps.settings_app.utils import set_setting

pytestmark = pytest.mark.django_db(transaction=True)
SECRET = "t" * 40 + "-blu-test-secret"


@pytest.fixture(autouse=True)
def quiet(monkeypatch, settings):
    from apps.common import staff_alert
    from apps.notifications import live
    from apps.orders import tasks

    settings.BLU_PUSH_SECRET = SECRET
    alerts, events = [], []
    monkeypatch.setattr(staff_alert, "alert_staff", lambda text, **kw: alerts.append((text, kw)) or 1)
    from apps.agency import notify

    monkeypatch.setattr(notify, "alert_staff", lambda text, **kw: alerts.append((text, kw)) or 1)
    monkeypatch.setattr(live, "push_payments_event", lambda e, **d: events.append((e, d)))
    monkeypatch.setattr(tasks.fulfill_order, "delay", lambda *_: None)
    set_setting("agency_portal_enabled", True, ValueType.BOOL)
    return {"alerts": alerts, "events": events}


def reseller(username):
    token = secrets.token_urlsafe(16)
    ResellerSession.objects.create(username=username, key_hash=portal._hash(token),
                                   expires_at=timezone.now() + timedelta(days=1))
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Agency {token}")
    return c


def sms(toman):
    SmsSource.objects.get_or_create(phone_number="+989999987641", defaults={"description": "blu"})
    device, _ = SmsAppDevice.objects.get_or_create(name="iPhone", defaults={"is_active": True})
    c = APIClient()
    c.credentials(HTTP_X_DEVICE_TOKEN=device.api_token)
    text = f"بلو\nواریز پول\nپویا عزیز،{int(toman) * 10:,} ریال به حساب شخصی شما نشست.\nموجودی: 1 ریال"
    return c.post("/api/v1/payments/sms/inbound/", {"text": text, "sender": "+989999987641"}, format="json").data


def balance(name):
    return ledger.balances().get(name, Decimal(0))


# ------------------------------------------------------------------ invoices per charge type
def test_staff_limit_raise_issues_an_invoice_and_no_price_blocks_it(pg, quiet):  # noqa: F811
    boss = staff_client(superadmin=True)
    r = boss.post("/api/v1/admin/agency/admins/g1-a/set-limit/", {"action": "add", "value_gb": 50}, format="json")
    assert r.status_code == 200, r.content
    inv = AgencyInvoice.objects.get()
    assert (inv.admin_username, inv.kind, inv.gb, inv.price_per_gb, inv.amount, inv.status) == \
        ("g1-a", "quota_charge", Decimal("50.0000"), Decimal("2000"), Decimal("100000"), "unpaid")
    assert inv.number == f"INV-{inv.id:06d}" and inv.ledger_entry.kind == "quota_charge"
    # an admin without a price: nothing on PasarGuard, no charge, Telegram to staff
    PanelAdmin.objects.create(username="g1-new", has_data_limit=True, admin_limit_bytes=10 * GB, last_limit_bytes=10 * GB)
    pg["fake"].add("g1-new", 10 * GB)
    puts = len(pg["fake"].puts)
    r = boss.post("/api/v1/admin/agency/admins/g1-new/set-limit/", {"action": "add", "value_gb": 5}, format="json")
    assert r.status_code in (400, 409) and "قیمت هر گیگ برای این ادمین تعریف نشده" in str(r.content.decode())
    assert len(pg["fake"].puts) == puts and AgencyInvoice.objects.count() == 1
    assert any("g1-new" in t and "5" in t and kw["perm"] == "agency.accounting" for t, kw in quiet["alerts"])


def test_manual_charge_with_gb_is_gb_times_price(pg):  # noqa: F811
    boss = staff_client(superadmin=True)
    url = "/api/v1/admin/agency/ledger/g1-a/entries/"
    assert boss.post(url, {"kind": "manual_charge", "amount": "1", "gb": "3"}, format="json").status_code == 201
    inv = AgencyInvoice.objects.get()
    assert inv.kind == "manual_charge" and inv.amount == Decimal("6000") and inv.gb == Decimal("3")
    r = boss.post("/api/v1/admin/agency/ledger/g1-unl/entries/", {"kind": "manual_charge", "amount": "1", "gb": "3"},
                  format="json")
    assert r.status_code in (400, 409) and AgencyInvoice.objects.count() == 1
    # voiding the charge voids its unpaid invoice
    boss.post(f"/api/v1/admin/agency/ledger/entries/{inv.ledger_entry_id}/void/", {"reason": "typo"}, format="json")
    inv.refresh_from_db()
    assert inv.status == "voided"


def test_group_manager_volume_approved_issues_an_invoice(pg, quiet):  # noqa: F811
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    manager_client().post(M + "admins/g1-a/add-volume/", {"gb": 10}, format="json")
    rid = VolumeRequest.objects.get().id
    assert boss.post(f"/api/v1/admin/agency/approvals/{rid}/approve/", {}, format="json").status_code == 200
    inv = AgencyInvoice.objects.get()
    assert inv.kind == "request" and inv.volume_request_id == rid and inv.amount == Decimal("20000")
    assert AgencyNotice.objects.filter(admin_username="g1-a", kind="invoice_issued").exists()
    assert AgencyNotice.objects.filter(manager__username="mona", kind="invoice_issued").exists()


def test_settlement_invoice_once_per_admin(pg):  # noqa: F811
    boss = staff_client(superadmin=True)
    LedgerEntry.objects.create(admin_username="g1-owner", kind="manual_charge", amount=Decimal("700000"),
                               date=ledger.today())          # a balance from before invoices
    q = boss.get("/api/v1/admin/agency/invoices/settlement/?admin=g1-owner").json()
    assert Decimal(str(q["amount"])) == Decimal("700000") and q["allowed"] is True
    r = boss.post("/api/v1/admin/agency/invoices/settlement/", {"admin": "g1-owner"}, format="json")
    assert r.status_code == 201 and r.json()["kind"] == "settlement" and r.json()["message_fa"]
    assert boss.post("/api/v1/admin/agency/invoices/settlement/", {"admin": "g1-owner"}, format="json").status_code == 409
    assert balance("g1-owner") == Decimal("700000")            # a settlement invoice adds no debt


# ------------------------------------------------------------------ admin requests from the portal
def test_admin_request_approve_raises_the_limit_and_invoices(pg, quiet):  # noqa: F811
    c = reseller("g1-a")
    q = c.get("/api/v1/agency/portal/requests/quote/?gb=25").json()
    assert q["amount"] == 50000 and q["missing_price"] is False
    r = c.post("/api/v1/agency/portal/requests/", {"gb": 25, "note": "for the weekend"}, format="json")
    assert r.status_code == 201, r.content
    req = VolumeRequest.objects.get()
    assert req.kind == "request" and req.requested_by == "g1-a" and req.group_name
    assert pg["fake"].admins["g1-a"]["data_limit"] == 100 * GB                # nothing live yet
    # in the Approvals queue, marked as an admin request
    boss = staff_client(superadmin=True)
    row = boss.get("/api/v1/admin/agency/approvals/").json()["results"][0]
    assert row["kind"] == "request" and row["requested_by"] == "g1-a" and row["note"] == "for the weekend"
    assert any("درخواست شارژ" in t and kw.get("buttons") for t, kw in quiet["alerts"])
    # a group manager can never approve it
    make_manager(boss, pg)
    assert manager_client().post(f"/api/v1/admin/agency/approvals/{req.id}/approve/", {}, format="json").status_code == 403
    assert boss.post(f"/api/v1/admin/agency/approvals/{req.id}/approve/", {}, format="json").status_code == 200
    assert pg["fake"].admins["g1-a"]["data_limit"] == 125 * GB
    assert PanelAdmin.objects.get(username="g1-a").last_limit_bytes == 125 * GB
    inv = AgencyInvoice.objects.get()
    assert inv.kind == "request" and inv.amount == Decimal("50000") and inv.volume_request_id == req.id
    # (the group now has a manager, so g1-a's portal is read-only — v1.35; check the row itself)
    req.refresh_from_db()
    assert req.status == "approved" and req.invoices.get() == inv
    assert AgencyNotice.objects.filter(admin_username="g1-a", kind="request_approved").exists()


def test_admin_request_reject_shows_the_reason_and_needs_a_price(pg):  # noqa: F811
    c = reseller("g1-a")
    c.post("/api/v1/agency/portal/requests/", {"gb": 5}, format="json")
    rid = VolumeRequest.objects.get().id
    boss = staff_client(superadmin=True)
    r = boss.post(f"/api/v1/admin/agency/approvals/{rid}/reject/", {"reason": "pay first", "confirm": True}, format="json")
    assert r.status_code == 200, r.content
    assert c.get("/api/v1/agency/portal/requests/").json()["results"][0]["reason"] == "pay first"
    n = AgencyNotice.objects.get(admin_username="g1-a", kind="request_rejected")
    assert "pay first" in n.body
    # no price → the form shows the error and no request is created
    q = reseller("g1-unl").get("/api/v1/agency/portal/requests/quote/?gb=5").json()
    assert q["missing_price"] is True and q["missing_price_fa"] == "قیمت هر گیگ برای این ادمین تعریف نشده"
    r = reseller("g1-unl").post("/api/v1/agency/portal/requests/", {"gb": 5}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "no_price"


# ------------------------------------------------------------------ paying
def _invoice(admin="g1-a", amount="100000"):
    e = LedgerEntry.objects.create(admin_username=admin, kind="manual_charge", amount=Decimal(amount), date=ledger.today())
    return billing.issue_for_entry(e)


def test_admin_pays_by_sms_exact(pg, quiet):  # noqa: F811
    inv = _invoice()
    c = reseller("g1-a")
    p = c.post("/api/v1/agency/portal/payments/", {"invoice_id": inv.id}, format="json").json()
    assert Decimal(str(p["amount"])) == Decimal("100000") and Decimal(str(p["amount_unique"])) > Decimal("100000")
    assert p["unique_expire_at"] and "cards" in p
    before = balance("g1-a")
    res = sms(Decimal(str(p["amount_unique"])))
    assert res["matched"] is True and res["agency_payment"] == p["number"]
    ap = AgencyPayment.objects.get()
    assert ap.status == "approved" and ap.method == "sms_auto" and ap.amount_unique_lock is None
    inv.refresh_from_db()
    assert inv.status == "paid"
    assert balance("g1-a") == before - Decimal("100000")             # the surcharge is not debt
    assert AgencyNotice.objects.filter(admin_username="g1-a", kind="payment_approved").exists()
    assert any("خودکار تأیید شد" in t for t, _ in quiet["alerts"])
    # the same deposit again is a duplicate, never approved twice
    assert sms(Decimal(str(p["amount_unique"])))["reason"] == "duplicate"


def test_manager_pays_several_invoices_by_blu(pg, quiet):  # noqa: F811
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    a, b = _invoice("g1-a", "100000"), _invoice("g1-owner", "50000")
    other = _invoice("g2-owner", "70000")                              # not the manager's group
    mc = manager_client()
    lst = mc.get(M + "invoices/").json()
    assert {r["admin"] for r in lst["results"]} == {"g1-a", "g1-owner"} and Decimal(str(lst["unpaid_total"])) == 150000
    assert mc.post(M + "payments/", {"invoice_ids": [a.id, other.id]}, format="json").status_code == 403
    p = mc.post(M + "payments/", {"invoice_ids": [a.id, b.id]}, format="json").json()
    assert Decimal(str(p["amount"])) == Decimal("150000") and len(p["invoices"]) == 2
    post([item(int(Decimal(str(p["amount_unique"]))), id="AGB1")])
    ap = AgencyPayment.objects.get()
    assert ap.status == "approved" and ap.method == "blu_auto" and ap.blu_transaction.bank_id == "AGB1"
    assert set(AgencyInvoice.objects.filter(pk__in=[a.id, b.id]).values_list("status", flat=True)) == {"paid"}
    assert balance("g1-a") == 0 and balance("g1-owner") == 0
    row = boss.get("/api/v1/admin/payments/blu-transactions/").json()["results"][0]
    assert row["agency_payment"]["number"] == ap.number and row["status"] == "matched"
    assert AgencyNotice.objects.filter(manager__username="mona", kind="payment_approved").exists()


def test_rounded_amount_with_receipt_keeps_the_shortfall_owed(pg, quiet):  # noqa: F811
    inv = _invoice("g1-a", "249000")
    c = reseller("g1-a")
    p = c.post("/api/v1/agency/portal/payments/", {"invoice_id": inv.id}, format="json").json()
    up = c.post(f"/api/v1/agency/portal/payments/{p['id']}/receipt/",
                {"receipt_image": _png()}, format="multipart")
    assert up.status_code == 200, up.content
    assert AgencyInvoice.objects.get(pk=inv.id).status == "pending"
    deposit = Decimal(str(p["amount_unique"])) - 2000                   # v1.44.1: at most 2,000 T below
    sms(deposit)
    ap = AgencyPayment.objects.get()
    assert ap.status == "approved" and ap.auto_rule == "rounded" and ap.auto_reason["receipt"] is True
    owed = Decimal("249000") - deposit                                  # what the deposit did not cover stays owed
    assert balance("g1-a") == owed and ap.shortfall == owed


def test_receipt_then_manual_approve_or_reject(pg, quiet):  # noqa: F811
    inv = _invoice()
    c = reseller("g1-a")
    p = c.post("/api/v1/agency/portal/payments/", {"invoice_id": inv.id}, format="json").json()
    c.post(f"/api/v1/agency/portal/payments/{p['id']}/receipt/", {"receipt_image": _png(), "receipt_ref": "123456"},
           format="multipart")
    assert any("رسید واریز نماینده" in t for t, _ in quiet["alerts"])
    clerk = staff_client(["agency.view"], name="viewer")
    assert clerk.post(f"/api/v1/admin/agency/payments/{p['id']}/approve/", {}, format="json").status_code == 403
    payer = staff_client(["agency.view", "agency.payments"], name="payer")
    q = payer.get("/api/v1/admin/agency/payments/").json()
    assert q["review"] == 1 and q["results"][0]["receipt_url"]
    assert payer.post(f"/api/v1/admin/agency/payments/{p['id']}/reject/", {"reason": "blurry"}, format="json").status_code == 200
    assert AgencyInvoice.objects.get(pk=inv.id).status == "unpaid"
    assert AgencyNotice.objects.filter(admin_username="g1-a", kind="payment_rejected", body__contains="blurry").exists()
    p2 = c.post("/api/v1/agency/portal/payments/", {"invoice_id": inv.id}, format="json").json()
    c.post(f"/api/v1/agency/portal/payments/{p2['id']}/receipt/", {"receipt_image": _png()}, format="multipart")
    r = payer.post(f"/api/v1/admin/agency/payments/{p2['id']}/approve/", {}, format="json")
    assert r.status_code == 200 and r.json()["message_fa"]
    assert AgencyInvoice.objects.get(pk=inv.id).status == "paid" and balance("g1-a") == 0


def test_payer_scope(pg):  # noqa: F811
    inv = _invoice("g1-owner")
    assert reseller("g1-a").post("/api/v1/agency/portal/payments/", {"invoice_id": inv.id},
                                 format="json").status_code == 403           # not my account
    assert reseller("g1-owner").post("/api/v1/agency/portal/payments/", {"invoice_id": inv.id},
                                     format="json").status_code == 201
    # a manager whose role lacks agency.gm.invoices gets 403
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    from apps.accounts.models import Role

    role = Role.objects.get(name="Group manager")
    role.permissions.remove(*role.permissions.filter(code="agency.gm.invoices"))
    assert manager_client().get(M + "invoices/").status_code == 403


def test_no_collision_with_customer_unique_amounts(pg):  # noqa: F811
    from apps.accounts.models import User
    from apps.orders.services import OrderError, create_order
    from apps.plans.models import Plan

    set_setting("unique_amount_min", 500, "int")
    set_setting("unique_amount_max", 500, "int")                       # only ONE possible surcharge
    plan = Plan.objects.create(name_fa="p", price=Decimal("100000"), data_limit=GB, duration_days=30)
    o = create_order(user=User.objects.create_user("cu1", "Str0ngPass!"), plan_id=plan.id, requested_account_name="cu1")
    assert o.amount_unique == Decimal("100500")
    inv = _invoice("g1-a", "100000")
    with pytest.raises(billing.BillingError) as e:                     # 100,500 is the customer's
        billing.create_payment([inv.id], payer_kind="admin", payer_username="g1-a", allowed_admins=["g1-a"])
    assert e.value.code == "busy"
    # the other way round: an agency payment holds 120,500 → a customer order cannot get it
    inv2 = _invoice("g1-a", "120000")
    ap = billing.create_payment([inv2.id], payer_kind="admin", payer_username="g1-a", allowed_admins=["g1-a"])
    assert ap.amount_unique == Decimal("120500")
    plan2 = Plan.objects.create(name_fa="p2", price=Decimal("120000"), data_limit=GB, duration_days=30)
    with pytest.raises(OrderError):
        create_order(user=User.objects.create_user("cu2", "Str0ngPass!"), plan_id=plan2.id, requested_account_name="cu2")


def test_agency_payments_stay_out_of_customer_revenue(pg, quiet):  # noqa: F811
    boss = staff_client(superadmin=True)
    rev0 = boss.get("/api/v1/admin/accounting/?period=monthly").json()["revenue"]
    tx0 = boss.get("/api/v1/admin/transactions/").json()["count"]
    inv = _invoice()
    p = billing.create_payment([inv.id], payer_kind="admin", payer_username="g1-a", allowed_admins=["g1-a"])
    sms(p.amount_unique)
    assert AgencyPayment.objects.get().status == "approved"
    assert boss.get("/api/v1/admin/accounting/?period=monthly").json()["revenue"] == rev0
    assert boss.get("/api/v1/admin/transactions/").json()["count"] == tx0
    assert boss.get("/api/v1/admin/payments/pending/").json()["count"] == 0 and not Payment.objects.exists()
    lst = boss.get("/api/v1/admin/agency/payments/?status=all").json()
    assert lst["results"][0]["number"] == p.number


def test_near_miss_goes_to_review_never_approved(pg, quiet):  # noqa: F811
    inv = _invoice()
    p = billing.create_payment([inv.id], payer_kind="admin", payer_username="g1-a", allowed_admins=["g1-a"])
    res = sms(p.amount_unique - 9000)                                  # within 20 %, no receipt
    assert res["reason"] == "amount mismatch" and res["agency_payment"] == p.number
    p.refresh_from_db()
    assert p.status == "pending_review" and p.mismatch_kind == "less"
    assert AgencyInvoice.objects.get(pk=inv.id).status == "pending"
    assert any("مبلغ نامطابق (نماینده)" in t for t, _ in quiet["alerts"])


def _png():
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (secrets.randbelow(255), 20, 30)).save(buf, format="PNG")
    buf.seek(0)
    f = ContentFile(buf.read(), name="r.png")
    return f


def test_v1441_agency_over_payment_is_rounded_without_evidence(pg, quiet):  # noqa: F811
    """v1.44.1: an agency payment paid a little MORE (≤ 2,000 T) is approved without a receipt; the invoices get their
    total (the extra is not credited, like the unique surcharge) and the row shows «بیشتر X»."""
    inv = _invoice()
    p = billing.create_payment([inv.id], payer_kind="admin", payer_username="g1-a", allowed_admins=["g1-a"])
    before = balance("g1-a")
    res = sms(p.amount_unique + 1000)
    assert res["matched"] is True and res["agency_payment"] == p.number
    p.refresh_from_db()
    assert p.status == "approved" and p.auto_rule == "rounded" and p.paid_amount == p.amount_unique + 1000
    assert p.auto_reason["direction"] == "more" and p.shortfall is None
    assert AgencyInvoice.objects.get(pk=inv.id).status == "paid" and balance("g1-a") == before - Decimal("100000")
    assert billing.payment_row(p)["rounded_diff"] == Decimal("-1000")
    assert any("مبلغ گرد شده – بیشتر 1,000" in t for t, _ in quiet["alerts"])
