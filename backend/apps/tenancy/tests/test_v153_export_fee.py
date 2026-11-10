"""v1.53 — store exports (Phase 10) and the monthly store fee hook (Phase 12).

Export: only with our switch (`export_allowed`, which also puts `store.export` in the ceiling) + `store.export`; built in the
background inside the store; the zip holds ONLY the store's own rows (never our data, never another store's), no password
hashes / tokens, masked cards, our staff as «support»; one-time links bound to their host; one per 6 h for the store; our
staff can export any store from «فروشگاه»; files expire after 24 h; every step audited.
Fee: off by default; once a Jalali month → one agency invoice (kind store_fee) to the reseller; reminder; optional suspension
(off by default) and the store comes back by itself once paid.
"""
import io
import json
import zipfile
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, Staff, User
from apps.agency import ledger
from apps.agency.models import AgencyInvoice, AgencyNotice, LedgerEntry, PanelAdmin
from apps.common.models import AuditLog
from apps.crm.models import DiscountCode
from apps.orders.models import Order, OrderStatus, OrderType
from apps.payments_sms.models import BankCard, Payment, PaymentStatus
from apps.plans.models import Plan
from apps.tenancy import context, export, fees
from apps.tenancy import staff as S
from apps.tenancy.models import Tenant, TenantDomain, TenantExport, TenantFeeInvoice
from apps.tenancy.tests.test_phase8 import _boss, _client
from apps.tickets.models import Ticket, TicketMessage, TicketTopic

pytestmark = pytest.mark.django_db
HOST, HOST_B = "shop-x.example", "shop-y.example"
MINE, OTHER, OURS = "ZZMINE", "ZZOTHER", "ZZOURS"
STORE_API = "/api/v1/admin/store-export/"
CARD = "6037991234567890"


@pytest.fixture
def codes(_default_tenant):
    for c in sorted(S.STORE_CODES | {"agency.manage", "agency.view", "agency.accounting"}):
        Permission.objects.get_or_create(code=c, defaults={"name": c})


@pytest.fixture
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def _store(slug, host, reseller):
    t = Tenant.objects.create(slug=slug, name=f"Store {slug}", status="active", reseller_username=reseller,
                              permission_ceiling=sorted(S.STORE_CODES - {"store.export"}))
    TenantDomain.objects.create(tenant=t, host=host, state="active")
    PanelAdmin.objects.create(username=reseller)
    return t


def _fill(mark, our_staff=None, store_staff=None):
    """One row of every exported kind, in the CURRENT tenant, marked with `mark`."""
    u = User.objects.create_user(f"{mark.lower()}_u", "Str0ngPass!", name=f"{mark} customer", bank_card_number=CARD,
                                 phone="09120000000")
    plan = Plan.objects.create(name_fa=f"{mark} plan", name_en=f"{mark} plan", price=Decimal(100000), duration_days=30)
    card = BankCard.objects.create(card_number=CARD, holder_name=f"{mark} holder")
    o = Order.objects.create(user=u, plan=plan, type=OrderType.NEW, status=OrderStatus.COMPLETED, amount=Decimal(100000),
                             amount_unique=Decimal(100123), unique_expire_at=timezone.now() + timedelta(minutes=10),
                             requested_account_name=f"{mark.lower()}acc")
    Payment.objects.create(order=o, amount=Decimal(100123), status=PaymentStatus.APPROVED, method="card_manual",
                           bank_card=card, receipt_ref=f"{mark}REF", confirmed_at=timezone.now(), confirmed_by_staff=our_staff)
    topic = TicketTopic.objects.create(name_fa=f"{mark} topic", name_en=f"{mark} topic")
    tk = Ticket.objects.create(user=u, topic=topic, subject=f"{mark} ticket")
    TicketMessage.objects.create(ticket=tk, author_user=u, body=f"{mark} question")
    if our_staff:
        TicketMessage.objects.create(ticket=tk, author_staff=our_staff, body=f"{mark} our answer")
    if store_staff:
        TicketMessage.objects.create(ticket=tk, author_staff=store_staff, body=f"{mark} store answer")
    DiscountCode.objects.create(code=f"{mark}OFF")
    return u


def _zip(content: bytes) -> dict:
    zf = zipfile.ZipFile(io.BytesIO(content))
    return {n: zf.read(n) for n in zf.namelist()}


def _allow(boss, reseller="resx"):
    r = boss.patch(f"/api/v1/admin/agency/panel-admins/{reseller}/store/", {"export_allowed": True}, format="json")
    assert r.status_code == 200, r.content


@pytest.fixture
def world(codes, media):
    """Store X (ours to export), store Y (must never leak), and our own data."""
    ours = Staff.objects.create(username="our-agent")
    x = _store("x", HOST, "resx")
    y = _store("y", HOST_B, "resy")
    owner, _ = S.ensure_owner(x, "xowner")
    _fill(OURS, our_staff=ours)
    with context.tenant_context(x.pk):
        _fill(MINE, our_staff=ours, store_staff=owner)
    with context.tenant_context(y.pk):
        _fill(OTHER)
    return {"x": x, "y": y, "owner": owner, "ours": ours}


# ------------------------------------------------------------------ export
def test_store_export_needs_our_switch_and_holds_only_its_own_data(world, django_capture_on_commit_callbacks):
    x, owner = world["x"], world["owner"]
    c = _client(owner, HOST)
    assert c.get(STORE_API).status_code == 403                                 # store.export not in the ceiling yet
    boss = _boss()
    _allow(boss)
    x.refresh_from_db()
    assert "store.export" in x.permission_ceiling                             # the switch also sets the ceiling
    owner = Staff.objects.get(pk=owner.pk)
    c = _client(owner, HOST)
    st = c.get(STORE_API).json()
    assert st["allowed"] is True and st["results"] == [] and st["next_allowed_at"] is None
    with django_capture_on_commit_callbacks(execute=True):
        r = c.post(STORE_API, {}, format="json")
    assert r.status_code == 202, r.content
    row = c.get(STORE_API).json()["results"][0]
    assert row["state"] == "ready" and row["progress"] == 100 and row["counts"]["customers"] == 1
    assert row["counts"]["ticket_messages"] == 3 and row["requested_by"] == "xowner"

    link = c.post(f"{STORE_API}{row['id']}/link/", {}, format="json").json()["url"]
    resp = APIClient(HTTP_HOST=HOST).get(link)                                 # a plain browser download, no token
    assert resp.status_code == 200 and resp["Content-Disposition"].startswith('attachment; filename="x-backup-')
    files = _zip(b"".join(resp.streaming_content))
    blob = b"".join(v for k, v in files.items() if k.startswith(("json/", "csv/", "manifest"))).decode("utf-8", "replace")
    assert MINE in blob and OURS not in blob and OTHER not in blob             # never our data, never store Y's
    assert {"manifest.json", "README.txt", "json/customers.json", "csv/customers.csv", "json/payments.json",
            "json/discount_codes.json", "json/plans.json", "json/branding.json", "json/settings.json"} <= set(files)
    for secret in ("password", "token", "secret", "Str0ngPass", CARD, "our-agent", "panel_id"):
        assert secret not in blob, secret                                       # no hashes, tokens, full cards, our names
    customers = json.loads(files["json/customers.json"])
    assert customers[0]["bank_card_number"] == "************7890"
    pays = json.loads(files["json/payments.json"])
    assert pays[0]["card"] == "************7890" and pays[0]["confirmed_by_staff"] == "support"
    authors = {m["body"]: m["author_staff"] for m in json.loads(files["json/ticket_messages.json"])}
    assert authors[f"{MINE} our answer"] == "support" and authors[f"{MINE} store answer"] == "xowner"
    assert files["csv/customers.csv"].startswith("﻿".encode())            # Excel opens Persian text correctly
    for action in ("store.export_requested", "store.export_ready", "store.export_link", "store.export_downloaded"):
        assert AuditLog.objects.filter(action=action).exists(), action


def test_the_link_works_once_and_only_on_its_own_host(world, django_capture_on_commit_callbacks):
    x, y = world["x"], world["y"]
    boss = _boss()
    _allow(boss)
    c = _client(Staff.objects.get(pk=world["owner"].pk), HOST)
    with django_capture_on_commit_callbacks(execute=True):
        e_id = c.post(STORE_API, {}, format="json").json()["export"]["id"]
    url = c.post(f"{STORE_API}{e_id}/link/", {}, format="json").json()["url"]
    assert APIClient().get(url).status_code == 410                             # a store link never works on our host
    assert APIClient(HTTP_HOST=HOST_B).get(url).status_code == 404             # nor on another store's domain
    assert APIClient(HTTP_HOST=HOST).get(url).status_code == 200
    assert APIClient(HTTP_HOST=HOST).get(url).status_code == 410               # spent
    token = url.rstrip("/").rsplit("/", 1)[1]
    bad = f"/api/v1/exports/download/{y.pk}/{token}/"
    assert APIClient(HTTP_HOST=HOST).get(bad).status_code == 404
    # a new link ends the previous one
    u1 = c.post(f"{STORE_API}{e_id}/link/", {}, format="json").json()["url"]
    u2 = c.post(f"{STORE_API}{e_id}/link/", {}, format="json").json()["url"]
    assert APIClient(HTTP_HOST=HOST).get(u1).status_code == 410
    assert APIClient(HTTP_HOST=HOST).get(u2).status_code == 200
    # our staff's own link («فروشگاه») works on our host only
    base = "/api/v1/admin/agency/panel-admins/resx/store/exports/"
    ours = boss.post(f"{base}{e_id}/link/", {}, format="json").json()["url"]
    assert APIClient(HTTP_HOST=HOST).get(ours).status_code == 410
    assert APIClient().get(ours).status_code == 200
    with context.tenant_context(x.pk):
        assert TenantExport.objects.get(pk=e_id).downloads == 3


def test_one_store_export_per_six_hours_one_at_a_time_and_none_from_other_stores(world, django_capture_on_commit_callbacks):
    x, y = world["x"], world["y"]
    boss = _boss()
    _allow(boss)
    c = _client(Staff.objects.get(pk=world["owner"].pk), HOST)
    with django_capture_on_commit_callbacks(execute=True):
        assert c.post(STORE_API, {}, format="json").status_code == 202
    r = c.post(STORE_API, {}, format="json")
    assert r.status_code == 429 and r.json()["code"] == "too_soon" and c.get(STORE_API).json()["next_allowed_at"]
    base = "/api/v1/admin/agency/panel-admins/resx/store/exports/"
    with django_capture_on_commit_callbacks(execute=False):                    # queued, not built: "busy"
        assert boss.post(base, {}, format="json").status_code == 202           # our staff: no 6-hour gap
    assert boss.post(base, {}, format="json").status_code == 409
    assert boss.get(base).json()["busy"] is True
    # store Y (no switch) sees none of X's exports and may not export
    with context.tenant_context(y.pk):
        assert TenantExport.objects.count() == 0
    y_owner, _ = S.ensure_owner(y, "yowner")
    assert _client(y_owner, HOST_B).get(STORE_API).status_code == 403
    # our host: the store page does not exist (our own store has no export)
    assert boss.get(STORE_API).status_code == 404
    # switching it off takes the permission away again
    boss.patch("/api/v1/admin/agency/panel-admins/resx/store/", {"export_allowed": False}, format="json")
    assert _client(Staff.objects.get(pk=world["owner"].pk), HOST).get(STORE_API).status_code == 403


def test_store_staff_without_the_permission_are_refused(world):
    x = world["x"]
    _allow(_boss())
    role = Role.objects.create(tenant=x, name="cashier")
    role.permissions.set(Permission.objects.filter(code="payment.view"))
    cashier = Staff.objects.create(username="xcashier", tenant=x, role=role)
    c = _client(cashier, HOST)
    assert c.get(STORE_API).status_code == 403 and c.post(STORE_API, {}, format="json").status_code == 403


def test_cleanup_deletes_expired_files_and_fails_stuck_jobs(world, media, django_capture_on_commit_callbacks):
    x = world["x"]
    boss = _boss()
    base = "/api/v1/admin/agency/panel-admins/resx/store/exports/"
    with django_capture_on_commit_callbacks(execute=True):
        e_id = boss.post(base, {}, format="json").json()["export"]["id"]
    with context.tenant_context(x.pk):
        e = TenantExport.objects.get(pk=e_id)
        assert (media / e.file).exists()
        TenantExport.objects.filter(pk=e_id).update(expires_at=timezone.now() - timedelta(minutes=1))
        stuck = TenantExport.objects.create(state=TenantExport.RUNNING)
        TenantExport.objects.filter(pk=stuck.pk).update(created_at=timezone.now() - timedelta(hours=3))
    out = export.cleanup()
    assert out[x.pk] == {"expired": 1, "failed": 1}
    with context.tenant_context(x.pk):
        assert TenantExport.objects.get(pk=e_id).state == "expired" and not (media / e.file).exists()
        assert TenantExport.objects.get(pk=stuck.pk).state == "failed"
    assert boss.post(f"{base}{e_id}/link/", {}, format="json").status_code == 410


def test_export_endpoints_are_ours_only_on_our_host(world):
    owner = world["owner"]
    _allow(_boss())
    c = _client(Staff.objects.get(pk=owner.pk), HOST)
    assert c.get("/api/v1/admin/agency/panel-admins/resx/store/exports/").status_code in (403, 404)
    assert c.patch("/api/v1/admin/agency/panel-admins/resx/store/fee/", {"amount": 1}, format="json").status_code in (403, 404)


# ------------------------------------------------------------------ fee
FEE = "/api/v1/admin/agency/panel-admins/resx/store/fee/"


@pytest.fixture
def fee_store(codes):
    t = _store("x", HOST, "resx")
    return t


def test_fee_is_off_by_default_and_needs_the_accounting_permission(fee_store):
    assert fees.run() == {"issued": [], "reminded": [], "suspended": [], "resumed": []}
    boss = _boss()
    assert boss.get(FEE).json()["fee"]["enabled"] is False
    role = Role.objects.create(name="mgr")
    role.permissions.set(Permission.objects.filter(code__in=["agency.view", "agency.manage"]))
    mgr = Staff.objects.create(username="mgr-only", role=role)
    assert _client(mgr).patch(FEE, {"amount": 500000}, format="json").status_code == 403
    r = boss.patch(FEE, {"enabled": True}, format="json")
    assert r.status_code == 400 and r.json()["field"] == "amount"
    r = boss.patch(FEE, {"enabled": True, "amount": 500000}, format="json")
    assert r.status_code == 400 and r.json()["field"] == "next_due"
    yesterday = (fees.tehran_today() - timedelta(days=1)).isoformat()
    assert boss.patch(FEE, {"amount": 500000, "next_due": yesterday}, format="json").status_code == 400


def test_monthly_invoice_reminder_suspension_and_resume(fee_store, monkeypatch):
    sent = []
    from apps.common import staff_alert

    monkeypatch.setattr(staff_alert, "alert_staff", lambda text, **kw: sent.append((text, kw)) or 1)
    boss = _boss()
    today = fees.tehran_today()
    r = boss.patch(FEE, {"enabled": True, "amount": "500,000", "next_due": today.isoformat(), "remind_after_days": 2},
                   format="json")
    assert r.status_code == 200, r.content
    assert AuditLog.objects.filter(action="store.fee_updated").exists()

    out = fees.run(today)
    assert out["issued"] == [f"x:{fees.period(today)}"]
    inv = AgencyInvoice.objects.get(admin_username="resx")
    assert inv.kind == "store_fee" and inv.amount == 500000 and inv.status == "unpaid"
    from apps.agency.billing import invoice_row

    assert invoice_row(inv)["source"] == "store_fee"
    entry = LedgerEntry.objects.get(admin_username="resx")
    assert entry.kind == "manual_charge" and entry.note.startswith("store monthly fee ")
    assert fees.run(today)["issued"] == []                                      # once per month
    row = boss.get(FEE).json()["fee"]
    assert row["next_due"] == fees.add_month(today).isoformat() and row["invoices"][0]["invoice"] == inv.number
    assert any(kw.get("platform") for _t, kw in sent)                          # we hear about it (silent)

    # the store's dashboard shows it to the store
    owner, _ = S.ensure_owner(fee_store, "xowner")
    d = _client(owner, HOST).get("/api/v1/admin/dashboard/").json()
    assert d["fee_due"]["count"] == 1 and d["fee_due"]["suspend_on"] is None

    # reminder after 2 days, once
    assert fees.run(today + timedelta(days=1))["reminded"] == []
    assert fees.run(today + timedelta(days=2))["reminded"] == [f"x:{fees.period(today)}"]
    assert fees.run(today + timedelta(days=3))["reminded"] == []
    assert AgencyNotice.objects.filter(admin_username="resx", kind="store_fee_due").count() == 1
    # suspension is off by default: a month late, the store stays active
    assert fees.run(today + timedelta(days=20))["suspended"] == []
    fee_store.refresh_from_db()
    assert fee_store.status == "active"

    # switched on: suspended N days after the due date; the store's domain answers 404
    boss.patch(FEE, {"suspend_enabled": True, "suspend_after_days": 5}, format="json")
    assert fees.run(today + timedelta(days=4))["suspended"] == []
    assert fees.run(today + timedelta(days=5))["suspended"] == [f"x:{fees.period(today)}"]
    fee_store.refresh_from_db()
    assert fee_store.status == "suspended"
    assert AuditLog.objects.filter(action="store.fee_suspended").exists()
    assert APIClient(HTTP_HOST=HOST).get("/api/v1/config/").status_code == 404
    assert boss.get(FEE).json()["fee"]["suspended_by_fee"] is True

    # paid (a ledger payment settles the invoice) → active again by itself
    ledger.add_entry("resx", LedgerEntry.KIND_PAYMENT, 500000, today, method="card", by="test")
    inv.refresh_from_db()
    assert inv.status == "paid"
    assert fees.run(today + timedelta(days=6))["resumed"] == ["x"]
    fee_store.refresh_from_db()
    assert fee_store.status == "active"
    assert AuditLog.objects.filter(action="store.fee_resumed").exists()


def test_a_store_our_staff_moved_meanwhile_is_left_alone(fee_store):
    boss = _boss()
    today = fees.tehran_today()
    boss.patch(FEE, {"enabled": True, "amount": 100000, "next_due": today.isoformat(), "suspend_enabled": True,
                     "suspend_after_days": 1}, format="json")
    fees.run(today)
    assert fees.run(today + timedelta(days=1))["suspended"]
    boss.patch("/api/v1/admin/agency/panel-admins/resx/store/", {"status": "closed"}, format="json")
    ledger.add_entry("resx", LedgerEntry.KIND_PAYMENT, 100000, today, method="card", by="test")
    assert fees.run(today + timedelta(days=2))["resumed"] == []
    fee_store.refresh_from_db()
    assert fee_store.status == "closed"
    assert TenantFeeInvoice.objects.get().resumed_at is not None               # no longer tracked


def test_jalali_months():
    from datetime import date

    import jdatetime

    j = lambda y, m, d: jdatetime.date(y, m, d).togregorian()           # noqa: E731
    assert fees.add_month(j(1405, 6, 31)) == j(1405, 7, 30)                    # shorter month → its last day
    assert fees.add_month(j(1405, 12, 15)) == j(1406, 1, 15)
    assert fees.period(j(1405, 9, 1)) == "1405-09"
    assert fees.first_of_next_month(date(2026, 11, 10)) == j(1405, 9, 1)
