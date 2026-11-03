"""v1.35 agency access: /agency/ sign-in is closed for owners of a group that has a group manager
(«لطفاً از پنل مدیریت گروه وارد شوید»), sub-admins of such a group only see their usage, direct admins
keep request + invoices + pay; per-admin override; an invoice is payable from ONE place only; a group
manager requests volume for an admin of its group (approval → limit + invoice to that admin)."""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.agency import billing, ledger
from apps.agency.models import AgencyInvoice, AgencyNotice, LedgerEntry, VolumeRequest
from apps.agency.tests.test_group_managers import GB, M, make_manager, manager_client, pg, staff_client  # noqa: F401
from apps.agency.tests.test_invoices import quiet, reseller  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
P = "/api/v1/agency/portal/"


def login(username):
    return APIClient().post(P + "login/", {"username": username, "password": "pw"}, format="json")


def _invoice(admin, amount="100000"):
    e = LedgerEntry.objects.create(admin_username=admin, kind="manual_charge", amount=Decimal(amount), date=ledger.today())
    return billing.issue_for_entry(e)


def test_owner_of_a_managed_group_signs_in_at_the_panel(pg, quiet):  # noqa: F811
    assert login("g1-owner").status_code == 200                     # no manager yet: unchanged
    c = reseller("g1-owner")
    assert c.get(P + "me/").status_code == 200
    make_manager(staff_client(superadmin=True), pg)                 # Vox-like group gets a manager
    r = login("g1-owner")
    assert r.status_code == 403 and r.json()["code"] == "use_panel"
    assert r.json()["detail_fa"] == "لطفاً از پنل مدیریت گروه وارد شوید" and r.json()["panel_url"].endswith("/")
    assert c.get(P + "me/").status_code == 403                      # an open session follows the policy too


def test_sub_admin_of_a_managed_group_is_read_only(pg, quiet):  # noqa: F811
    make_manager(staff_client(superadmin=True), pg)
    assert login("g1-a").status_code == 200
    c = reseller("g1-a")
    me = c.get(P + "me/").json()
    assert me["access"]["mode"] == "readonly" and me["access"]["manager"]
    assert [a["username"] for a in me["accounts"]] == ["g1-a"] and me["balances"] == {}
    for method, path, body in [("get", "invoices/", None), ("get", "requests/", None), ("post", "requests/", {"gb": 5}),
                               ("get", "requests/quote/?gb=5", None), ("post", "payments/", {"invoice_id": 1}),
                               ("get", "statement/", None)]:
        r = getattr(c, method)(P + path, body, format="json") if body else getattr(c, method)(P + path)
        assert r.status_code == 403, (path, r.status_code)
    assert not VolumeRequest.objects.exists()


def test_direct_admin_unchanged_and_override(pg, quiet):  # noqa: F811
    boss = staff_client(superadmin=True)
    me = reseller("g2-owner").get(P + "me/").json()
    assert me["access"]["mode"] == "full"
    assert reseller("g2-owner").post(P + "requests/", {"gb": 5}, format="json").status_code == 201
    # override off: no sign-in even for a direct admin
    r = boss.put("/api/v1/admin/agency/portal-access/g2-owner/", {"mode": "off"}, format="json")
    assert r.status_code == 200 and r.json()["mode"] == "blocked"
    assert login("g2-owner").status_code == 403
    # override on: the owner of a managed group may sign in (usage only)
    make_manager(boss, pg)
    boss.put("/api/v1/admin/agency/portal-access/g1-owner/", {"mode": "on"}, format="json")
    assert login("g1-owner").status_code == 200
    assert reseller("g1-owner").get(P + "me/").json()["access"]["mode"] == "readonly"
    assert staff_client(["agency.view"], name="v").put("/api/v1/admin/agency/portal-access/g1-owner/", {"mode": "off"},
                                                        format="json").status_code == 403


def test_an_invoice_is_paid_from_one_place_only(pg, quiet):  # noqa: F811
    boss = staff_client(superadmin=True)
    inv = _invoice("g1-a")
    make_manager(boss, pg)
    # the admin (even with the override) cannot pay what the manager pays
    boss.put("/api/v1/admin/agency/portal-access/g1-a/", {"mode": "on"}, format="json")
    with pytest.raises(billing.BillingError) as e:
        billing.create_payment([inv.id], payer_kind="admin", payer_username="g1-a", allowed_admins=["g1-a"])
    assert e.value.code == "forbidden"
    assert manager_client().post(M + "payments/", {"invoice_ids": [inv.id]}, format="json").status_code == 201
    # a direct admin's invoice is never the manager's
    direct = _invoice("g2-owner")
    assert manager_client().post(M + "payments/", {"invoice_ids": [direct.id]}, format="json").status_code == 403
    with pytest.raises(billing.BillingError):
        billing.create_payment([direct.id], payer_kind="manager", payer_username="mona", allowed_admins=["g2-owner"])


def test_manager_requests_volume_for_a_sub_admin(pg, quiet):  # noqa: F811
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    mc = manager_client()
    q = mc.get(M + "requests/?quote=1&admin=g1-a&gb=30").json()
    assert q["amount"] == 60000
    assert mc.post(M + "requests/", {"admin": "g2-owner", "gb": 5}, format="json").status_code == 403   # other group
    r = mc.post(M + "requests/", {"admin": "g1-a", "gb": 30, "note": "new customers"}, format="json")
    assert r.status_code == 201, r.content
    req = VolumeRequest.objects.get()
    assert req.kind == "request" and req.manager.username == "mona" and req.requested_by == "mona" and req.admin_username == "g1-a"
    assert pg["fake"].admins["g1-a"]["data_limit"] == 100 * GB                 # not live before approval
    assert any("مدیر گروه mona برای" in t and kw.get("buttons") for t, kw in quiet["alerts"])
    row = boss.get("/api/v1/admin/agency/approvals/").json()["results"][0]
    assert row["kind"] == "request" and row["requested_by"] == "mona"
    assert boss.post(f"/api/v1/admin/agency/approvals/{req.id}/approve/", {}, format="json").status_code == 200
    assert pg["fake"].admins["g1-a"]["data_limit"] == 130 * GB
    inv = AgencyInvoice.objects.get()
    assert inv.admin_username == "g1-a" and inv.amount == Decimal("60000")
    assert AgencyNotice.objects.filter(manager__username="mona", kind="request_approved").exists()
    assert mc.get(M + "requests/").json()["results"][0]["invoice"] == inv.number
    # a role without the permission → 403
    role = Role.objects.get(name="Group manager")
    role.permissions.remove(*role.permissions.filter(code="agency.gm.request_volume"))
    assert manager_client().post(M + "requests/", {"admin": "g1-a", "gb": 1}, format="json").status_code == 403


def test_manager_sees_balances_and_pays_an_old_balance(pg, quiet):  # noqa: F811
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    LedgerEntry.objects.create(admin_username="g1-a", kind="manual_charge", amount=Decimal("90000"), date=ledger.today())
    mc = manager_client()
    d = mc.get(M + "invoices/").json()
    row = next(a for a in d["admins"] if a["admin"] == "g1-a")
    assert Decimal(str(row["old_balance"])) == Decimal("90000") and row["can_settle"] is True and row["payer"] == "manager"
    assert d["results"] == [] and d["groups"]                            # empty list, still the page data
    r = mc.post(M + "invoices/settlement/", {"admin": "g1-a"}, format="json")
    assert r.status_code == 201 and r.json()["kind"] == "settlement"
    assert mc.post(M + "invoices/settlement/", {"admin": "g2-owner"}, format="json").status_code == 403
    p = mc.post(M + "payments/", {"invoice_ids": [r.json()["id"]]}, format="json")
    assert p.status_code == 201
