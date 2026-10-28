"""Group managers: staff create them and assign groups + allowed inbounds (roles); a manager
sees only its groups, creates admins / adds volume (live on PasarGuard at once, pending
approval), changes password / inbounds within the allowed list; staff approve (→ quota
charge, linked in the limit history) or reject (→ volume taken back, no charge); the cap
blocks new volume; every forbidden action is 403; group statement; audit + activity.
PasarGuard is a small in-memory fake behind `responses`."""
import json
import re
from decimal import Decimal

import pytest
import responses
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, Staff
from apps.adminpanel.tokens import issue_tokens
from apps.agency import ledger, managers
from apps.agency.models import (AdminGroup, AdminLimitChange, GroupManager, LedgerEntry, PanelAdmin, VolumeRequest)
from apps.common.models import AuditLog
from apps.panel.models import Panel
from apps.settings_app.models import ValueType
from apps.settings_app.utils import set_setting

pytestmark = pytest.mark.django_db
GB = 1024 ** 3
BASE = "https://sigma.test"
CATALOG = {
    1: {"id": 1, "name": "owner", "is_owner": True, "inbounds": [], "all_inbounds": True},
    4: {"id": 4, "name": "operator wir", "is_owner": False, "inbounds": ["wirgard"], "all_inbounds": False},
    6: {"id": 6, "name": "operator pouya", "is_owner": False, "inbounds": ["Mix tun+cdn", "CDN ++"], "all_inbounds": False},
    7: {"id": 7, "name": "operator ali", "is_owner": False, "inbounds": ["ali tunel"], "all_inbounds": False},
}


class FakePanel:
    def __init__(self):
        self.admins = {}
        self.puts = []

    def add(self, username, limit, role=6, owner=False):
        self.admins[username] = {"username": username, "data_limit": limit, "status": "active", "is_disabled": False,
                                 "role": {"id": role, "name": CATALOG.get(role, {}).get("name", "x"), "is_owner": owner}}

    def install(self, rsps):
        rsps.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"})
        rsps.add_callback(responses.GET, f"{BASE}/api/admins", callback=self._list)
        rsps.add_callback(responses.POST, f"{BASE}/api/admin", callback=self._create)
        rsps.add_callback(responses.PUT, re.compile(rf"{BASE}/api/admin/.+"), callback=self._put)

    def _list(self, req):
        from urllib.parse import parse_qs, urlparse

        u = parse_qs(urlparse(req.url).query).get("username", [""])[0]
        rows = [a for k, a in self.admins.items() if k == u]
        return 200, {}, json.dumps({"admins": rows, "total": len(rows)})

    def _create(self, req):
        b = json.loads(req.body)
        self.created = getattr(self, "created", []) + [b]
        if b["username"] in self.admins:
            return 409, {}, json.dumps({"detail": "exists"})
        self.add(b["username"], b.get("data_limit") or 0, role=b["role_id"])
        return 200, {}, json.dumps(self.admins[b["username"]])

    def _put(self, req):
        from urllib.parse import unquote

        u = unquote(req.url.rsplit("/", 1)[1])
        b = json.loads(req.body)
        self.puts.append((u, b))
        a = self.admins[u]
        if "data_limit" in b:
            a["data_limit"] = b["data_limit"]
        if "role_id" in b:
            a["role"] = {"id": b["role_id"], "name": CATALOG[b["role_id"]]["name"], "is_owner": False}
        if "status" in b:
            a["status"], a["is_disabled"] = b["status"], b["status"] == "disabled"
        for k in ("support_url", "profile_title"):
            if k in b:
                a[k] = b[k]
        return 200, {}, json.dumps(a)


@pytest.fixture
def pg(monkeypatch):
    cache.clear()
    set_setting("agency_sync_enabled", True, ValueType.BOOL)
    Panel.objects.create(name="sigma", base_url=BASE, admin_username="u", admin_password_enc="p", is_active=True)
    monkeypatch.setattr(managers, "roles_catalog", lambda fresh=False: CATALOG)
    fake = FakePanel()
    for name, limit in (("g1-owner", 500 * GB), ("g1-a", 100 * GB), ("g2-owner", 300 * GB), ("other", 50 * GB)):
        fake.add(name, limit)
        PanelAdmin.objects.create(username=name, has_data_limit=True, admin_limit_bytes=limit, last_limit_bytes=limit,
                                  total_user_used=10 * GB, raw_data={"role": {"id": 6, "name": "operator pouya"}})
    fake.add("g1-unl", 0)
    PanelAdmin.objects.create(username="g1-unl", has_data_limit=False, admin_limit_bytes=0, last_limit_bytes=80 * GB)
    fake.add("g1-sudo", 0, role=1, owner=True)
    PanelAdmin.objects.create(username="g1-sudo", is_sudo=True)
    g1 = AdminGroup.objects.create(owner_username="g1-owner", member_usernames="g1-a,g1-unl,g1-sudo", name="Team one")
    g2 = AdminGroup.objects.create(owner_username="g2-owner", member_usernames="", name="Team two")
    for n in ("g1-owner", "g1-a", "g2-owner"):
        ledger.set_price(n, 2000, ledger.today())
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        fake.install(rsps)
        yield {"fake": fake, "g1": g1, "g2": g2, "rsps": rsps}


def staff_client(perms=None, superadmin=False, name="boss"):
    role = None
    if perms is not None:
        role = Role.objects.create(name=f"r-{name}")
        role.permissions.set([Permission.objects.get_or_create(code=c, defaults={"name": c})[0] for c in perms])
    s = Staff(username=name, role=role, is_superadmin=superadmin)
    s.set_password("x-Str0ng!")
    s.save()
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    return c


def make_manager(boss, pg, cap=None, roles=(6, 7), username="mona"):
    r = boss.post("/api/v1/admin/agency/managers/", {
        "username": username, "password": "mgr-Pass-123", "display_name": "Mona",
        "max_unapproved_gb": cap, "assignments": [{"group_id": pg["g1"].id, "role_ids": list(roles)}]}, format="json")
    assert r.status_code == 201, r.json()
    return r.json()


def manager_client(username="mona", password="mgr-Pass-123"):
    """v1.25: a group manager signs in to the main panel (staff login) and gets a staff JWT."""
    c = APIClient()
    r = c.post("/api/v1/admin/auth/login/", {"username": username, "password": password}, format="json")
    assert r.status_code == 200, r.json()
    assert r.json()["staff"]["group_manager"]["username"] == username
    perms = r.json()["staff"]["permissions"]                       # v1.27: the marker + its agency.gm.* abilities
    assert perms[0] == "agency.group_manager" and all(p.startswith("agency.gm.") for p in perms[1:])
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
    return c


M = "/api/v1/agency/manager/"


# ------------------------------------------------------------------ staff: managers
def test_staff_create_edit_disable_and_reset_password(pg):
    boss = staff_client(superadmin=True)
    row = make_manager(boss, pg, cap="300")
    assert row["assignments"][0]["role_ids"] == [6, 7] and row["assignments"][0]["roles"][0]["inbounds"] == ["Mix tun+cdn", "CDN ++"]
    assert Decimal(row["max_unapproved_gb"]) == Decimal("300")
    # an owner role can never be allowed
    bad = boss.patch(f"/api/v1/admin/agency/managers/{row['id']}/",
                     {"assignments": [{"group_id": pg["g1"].id, "role_ids": [1]}]}, format="json")
    assert bad.status_code == 400 and "owner" in bad.json()["detail"]
    mc = manager_client()
    assert mc.get(M + "me/").status_code == 200
    # disable → sessions end, login refused
    assert boss.patch(f"/api/v1/admin/agency/managers/{row['id']}/", {"is_active": False}, format="json").status_code == 200
    assert mc.get(M + "me/").status_code == 401
    assert APIClient().post("/api/v1/admin/auth/login/", {"username": "mona", "password": "mgr-Pass-123"},
                            format="json").status_code == 401
    boss.patch(f"/api/v1/admin/agency/managers/{row['id']}/", {"is_active": True, "max_unapproved_gb": ""}, format="json")
    assert GroupManager.objects.get().max_unapproved_gb is None                   # empty = no cap
    mc = manager_client()
    r = boss.post(f"/api/v1/admin/agency/managers/{row['id']}/password/", {}, format="json")
    new_pw = r.json()["password"]
    assert len(new_pw) >= 12
    assert mc.get(M + "me/").status_code == 401                                   # reset ends panel sessions
    manager_client(password=new_pw)
    logs = list(AuditLog.objects.filter(action__startswith="agency.managers.").values_list("action", flat=True))
    assert "agency.managers.created" in logs and "agency.managers.password_reset" in logs
    assert new_pw not in json.dumps(list(AuditLog.objects.values_list("detail", flat=True)))


def test_managing_managers_needs_agency_manage(pg):
    viewer = staff_client(perms=["agency.view"], name="viewer")
    assert viewer.get("/api/v1/admin/agency/managers/").status_code == 200
    assert viewer.post("/api/v1/admin/agency/managers/", {"username": "x"}, format="json").status_code == 403


# ------------------------------------------------------------------ manager portal: scope + actions
def test_manager_sees_only_its_groups(pg):
    make_manager(staff_client(superadmin=True), pg)
    me = manager_client().get(M + "me/").json()
    assert [g["name"] for g in me["groups"]] == ["Team one"]
    names = {a["username"] for a in me["groups"][0]["admins"]}
    assert names == {"g1-owner", "g1-a", "g1-unl", "g1-sudo"} and "g2-owner" not in names
    assert [r["id"] for r in me["groups"][0]["roles"]] == [6, 7]


def test_create_admin_is_live_and_pending(pg):
    make_manager(staff_client(superadmin=True), pg)
    mc = manager_client()
    r = mc.post(M + "admins/", {"group_id": pg["g1"].id, "username": "newbie", "password": "Secret-Pass#12",
                                "role_id": 7, "initial_gb": 50}, format="json")
    assert r.status_code == 201, r.json()
    assert pg["fake"].admins["newbie"]["data_limit"] == 50 * GB and pg["fake"].admins["newbie"]["role"]["id"] == 7
    assert "newbie" in AdminGroup.objects.get(pk=pg["g1"].id).get_members()
    req = VolumeRequest.objects.get()
    assert (req.kind, req.status, req.gb, req.new_limit_bytes, req.manager_username) == ("create", "pending", Decimal("50.0000"), 50 * GB, "mona")
    assert not LedgerEntry.objects.exists()                                  # no charge before approval
    h = AdminLimitChange.objects.get(admin_username="newbie")
    assert (h.action, h.source, h.staff) == ("create", "manager", "manager:mona") and req.limit_change == h
    log = AuditLog.objects.get(action="agency.manager.admin_created")
    assert log.staff_label == "manager:mona" and log.detail["group_id"] == pg["g1"].id and "Secret-Pass#12" not in json.dumps(log.detail)


def test_add_volume_then_approve_charges_and_links_history(pg):
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    mc = manager_client()
    r = mc.post(M + "admins/g1-a/add-volume/", {"gb": 200}, format="json")
    assert r.status_code == 200, r.json()
    assert pg["fake"].admins["g1-a"]["data_limit"] == 300 * GB                # live at once
    a = PanelAdmin.objects.get(username="g1-a")
    assert (a.admin_limit_bytes, a.last_limit_bytes) == (300 * GB, 300 * GB)
    lst = boss.get("/api/v1/admin/agency/approvals/").json()
    assert lst["pending"] == 1 and Decimal(str(lst["results"][0]["amount"])) == Decimal("400000")
    assert boss.get("/api/v1/admin/agency/approvals/badge/").json()["pending"] == 1
    rid = lst["results"][0]["id"]
    ok = boss.post(f"/api/v1/admin/agency/approvals/{rid}/approve/", {}, format="json")
    assert ok.status_code == 200, ok.json()
    e = LedgerEntry.objects.get()
    assert (e.kind, e.gb, e.amount, e.old_limit_bytes, e.new_limit_bytes) == ("quota_charge", Decimal("200.0000"), Decimal("400000"), 100 * GB, 300 * GB)
    assert AdminLimitChange.objects.get(admin_username="g1-a", action="add").ledger_entry == e
    assert boss.post(f"/api/v1/admin/agency/approvals/{rid}/approve/", {}, format="json").status_code == 409   # once only
    assert AuditLog.objects.filter(action="agency.approval.approved", detail__group_id=pg["g1"].id).exists()


def test_approve_without_price_asks_for_one(pg):
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    manager_client().post(M + "admins/", {"group_id": pg["g1"].id, "username": "fresh", "password": "Secret-Pass#12",
                                          "role_id": 6, "initial_gb": 10}, format="json")
    rid = VolumeRequest.objects.get().id
    r = boss.post(f"/api/v1/admin/agency/approvals/{rid}/approve/", {}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "no_price"
    r = boss.post(f"/api/v1/admin/agency/approvals/{rid}/approve/", {"price_per_gb": 1500}, format="json")
    assert r.status_code == 200 and LedgerEntry.objects.get().amount == Decimal("15000")


def test_reject_takes_the_volume_back_without_charge(pg):
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    manager_client().post(M + "admins/g1-a/add-volume/", {"gb": 40}, format="json")
    rid = VolumeRequest.objects.get().id
    assert boss.post(f"/api/v1/admin/agency/approvals/{rid}/reject/", {"reason": "no"}, format="json").status_code == 400  # confirm first
    r = boss.post(f"/api/v1/admin/agency/approvals/{rid}/reject/", {"reason": "too much", "confirm": True}, format="json")
    assert r.status_code == 200, r.json()
    assert pg["fake"].admins["g1-a"]["data_limit"] == 100 * GB and PanelAdmin.objects.get(username="g1-a").admin_limit_bytes == 100 * GB
    assert not LedgerEntry.objects.exists()
    assert VolumeRequest.objects.get().status == "rejected"
    assert AdminLimitChange.objects.filter(admin_username="g1-a", action="reduce", staff="boss").exists()


def test_reject_of_a_new_admin_never_makes_it_unlimited(pg):
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    manager_client().post(M + "admins/", {"group_id": pg["g1"].id, "username": "fresh", "password": "Secret-Pass#12",
                                          "role_id": 6, "initial_gb": 10}, format="json")
    rid = VolumeRequest.objects.get().id
    assert boss.post(f"/api/v1/admin/agency/approvals/{rid}/reject/", {"confirm": True}, format="json").status_code == 200
    assert pg["fake"].admins["fresh"]["data_limit"] == 1                       # 0 would be unlimited


def test_bulk_approve(pg):
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    mc = manager_client()
    for n in ("g1-a", "g1-owner"):
        assert mc.post(M + f"admins/{n}/add-volume/", {"gb": 5}, format="json").status_code == 200
    ids = list(VolumeRequest.objects.values_list("id", flat=True))
    r = boss.post("/api/v1/admin/agency/approvals/bulk-approve/", {"ids": ids}, format="json").json()
    assert sorted(r["approved"]) == sorted(ids) and LedgerEntry.objects.count() == 2


def test_cap_blocks_new_volume_until_approved(pg):
    boss = staff_client(superadmin=True)
    make_manager(boss, pg, cap="100")
    mc = manager_client()
    assert mc.post(M + "admins/g1-a/add-volume/", {"gb": 80}, format="json").status_code == 200
    r = mc.post(M + "admins/g1-a/add-volume/", {"gb": 30}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "cap_reached" and Decimal(r.json()["left_gb"]) == Decimal("20")
    assert pg["fake"].admins["g1-a"]["data_limit"] == 180 * GB                # the blocked one never reached PasarGuard
    boss.post(f"/api/v1/admin/agency/approvals/{VolumeRequest.objects.get().id}/approve/", {}, format="json")
    assert mc.post(M + "admins/g1-a/add-volume/", {"gb": 30}, format="json").status_code == 200


def test_password_and_inbounds_within_the_allowed_list(pg):
    make_manager(staff_client(superadmin=True), pg)
    mc = manager_client()
    assert mc.post(M + "admins/g1-a/password/", {"password": "New-Pass#9912"}, format="json").status_code == 200
    assert ("g1-a", {"password": "New-Pass#9912"}) in pg["fake"].puts
    r = mc.post(M + "admins/g1-a/inbounds/", {"role_id": 7}, format="json")
    assert r.status_code == 200 and r.json()["role"]["inbounds"] == ["ali tunel"]
    assert pg["fake"].admins["g1-a"]["role"]["id"] == 7
    acts = set(AuditLog.objects.filter(action__startswith="agency.manager.").values_list("action", flat=True))
    assert {"agency.manager.password_changed", "agency.manager.inbounds_changed"} <= acts
    assert "New-Pass#9912" not in json.dumps(list(AuditLog.objects.values_list("detail", flat=True)))


# ------------------------------------------------------------------ everything forbidden → 403
def test_every_forbidden_action_is_403(pg):
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    mc = manager_client()
    before = {k: v["data_limit"] for k, v in pg["fake"].admins.items()}
    checks = [
        ("post", "admins/g1-a/add-volume/", {"gb": -10}),                 # reduce
        ("post", "admins/g1-a/add-volume/", {"gb": 0}),                   # 0 = unlimited
        ("post", "admins/g1-unl/add-volume/", {"gb": 10}),                # admin is unlimited (staff only)
        ("post", "admins/g1-a/set-limit/", {"action": "set", "value_gb": 1}),
        ("post", "admins/g1-a/remove-limit/", {}),
        ("post", "admins/g1-a/reduce/", {"gb": 5}),
        ("post", "admins/g1-a/unlimited/", {}),
        ("delete", "admins/g1-a/", None),
        ("post", "admins/g1-a/delete/", {}),
        ("post", "admins/g1-a/role/", {"role_id": 1}),
        ("post", "admins/g1-a/inbounds/", {"role_id": 1}),               # owner role
        ("post", "admins/g1-a/inbounds/", {"role_id": 4}),               # not in the allowed list
        ("post", "admins/g1-sudo/password/", {"password": "Whatever-1"}),   # owner admin in the group
        ("post", "admins/g2-owner/add-volume/", {"gb": 10}),              # other group
        ("post", "admins/other/password/", {"password": "Whatever-1"}),   # admin in no group
        ("post", "admins/g2-owner/inbounds/", {"role_id": 6}),
        ("get", "admins/g2-owner/statement/", None),
        ("get", f"groups/{pg['g2'].id}/statement/", None),
        ("get", f"accounting/?group={pg['g2'].id}", None),
        ("get", f"activity/?group={pg['g2'].id}", None),
        ("post", "admins/", {"group_id": pg["g2"].id, "username": "x1x", "password": "Secret-Pass#12", "role_id": 6, "initial_gb": 5}),
        ("post", "admins/", {"group_id": pg["g1"].id, "username": "x2x", "password": "Secret-Pass#12", "role_id": 4, "initial_gb": 5}),
        ("post", "admins/", {"group_id": pg["g1"].id, "username": "x3x", "password": "Secret-Pass#12", "role_id": 6, "initial_gb": 0}),
        ("post", "payments/", {"admin": "g1-a", "amount": 1000}),
        ("post", "ledger/g1-a/entries/", {"kind": "payment", "amount": 1000}),
        ("post", "prices/", {"admin": "g1-a", "price_per_gb": 1}),
        ("post", "roles/", {}),
    ]
    for method, path, body in checks:
        r = getattr(mc, method)(M + path, body, format="json") if body is not None else getattr(mc, method)(M + path)
        assert r.status_code == 403, (method, path, r.status_code, r.content[:200])
    assert {k: v["data_limit"] for k, v in pg["fake"].admins.items()} == before   # nothing changed on PasarGuard
    assert not VolumeRequest.objects.exists() and not LedgerEntry.objects.exists()


def test_group_manager_staff_never_opens_the_rest_of_the_panel(pg):
    make_manager(staff_client(superadmin=True), pg)
    mc = manager_client()
    for method, path, body in [
        ("get", "/api/v1/admin/agency/", None),
        ("get", "/api/v1/admin/agency/admins/", None),
        ("get", "/api/v1/admin/agency/groups/", None),
        ("get", "/api/v1/admin/agency/ledger/groups/", None),
        ("get", f"/api/v1/admin/agency/ledger/groups/{pg['g2'].id}/statement/", None),
        ("post", "/api/v1/admin/agency/admins/g1-a/set-limit/", {"action": "add", "value_gb": 10}),
        ("post", "/api/v1/admin/agency/admins/g1-a/remove-limit/", {}),
        ("delete", "/api/v1/admin/agency/panel-admins/g1-a/", None),
        ("post", "/api/v1/admin/agency/ledger/g1-a/entries/", {"kind": "payment", "amount": 1, "method": "cash"}),
        ("post", "/api/v1/admin/agency/ledger/g1-a/prices/", {"price_per_gb": 1}),
        ("post", "/api/v1/admin/agency/approvals/bulk-approve/", {"ids": [1]}),
        ("get", "/api/v1/admin/agency/managers/", None),
        ("get", "/api/v1/admin/roles/", None),
        ("get", "/api/v1/admin/staff/", None),
        ("get", "/api/v1/admin/users/", None),
        ("get", "/api/v1/admin/transactions/", None),
        ("get", "/api/v1/admin/payments/pending/", None),
        ("get", "/api/v1/admin/accounting/", None),
        ("get", "/api/v1/admin/settings/", None),
        ("get", "/api/v1/admin/tickets/", None),
        ("get", "/api/v1/admin/crm/analytics/financial/", None),
    ]:
        r = getattr(mc, method)(path, body, format="json") if body is not None else getattr(mc, method)(path)
        assert r.status_code == 403, (method, path, r.status_code)
    # its own profile works (the panel needs it to draw the reduced menu)
    me = mc.get("/api/v1/admin/auth/me/").json()
    assert me["group_manager"]["username"] == "mona" and me["permissions"][0] == "agency.group_manager"
    assert all(p.startswith("agency.gm.") for p in me["permissions"][1:])


def _admin_routes():
    """Every concrete URL under /api/v1/admin/ (router + path routes), ids filled with 1."""
    import re

    from django.urls import URLPattern, URLResolver, get_resolver

    out = set()

    def walk(patterns, prefix):
        for p in patterns:
            route = str(p.pattern)
            if isinstance(p, URLResolver):
                walk(p.url_patterns, prefix + route)
            elif isinstance(p, URLPattern):
                full = prefix + route
                if "format" in full:
                    continue
                full = full.replace("^", "").replace("$", "")
                full = re.sub(r"<int:[^>]+>", "1", full)
                full = re.sub(r"<(?:str|path|slug):[^>]+>", "x1", full)
                full = re.sub(r"<[^>]+>", "x1", full)
                full = re.sub(r"\(\?P<[^>]+>[^)]*\)", "1", full)
                full = full.replace("\\.", ".")
                if any(ch in full for ch in "()[]*+?\\"):
                    continue
                out.add("/" + full)

    walk(get_resolver().url_patterns, "")
    return sorted(u for u in out if u.startswith("/api/v1/admin/"))


def test_every_other_panel_api_is_403_for_a_group_manager(pg):
    """Default-deny: a group-manager staff gets 403 on EVERY /api/v1/admin/ route (settings,
    customers, orders, payments, transactions, tickets, CRM, agency, other groups …) for
    every method — only its own profile and the login/refresh endpoints answer."""
    make_manager(staff_client(superadmin=True), pg)
    mc = manager_client()
    routes = _admin_routes()
    assert len(routes) > 100, len(routes)
    allowed = {"/api/v1/admin/auth/login/", "/api/v1/admin/auth/refresh/", "/api/v1/admin/auth/me/"}
    before = {k: v["data_limit"] for k, v in pg["fake"].admins.items()}
    bad = []
    for url in routes:
        if url in allowed:
            continue
        for method in ("get", "post", "put", "patch", "delete"):
            r = getattr(mc, method)(url, {}, format="json")
            if r.status_code != 403:
                bad.append((method, url, r.status_code))
    assert not bad, bad[:20]
    assert {k: v["data_limit"] for k, v in pg["fake"].admins.items()} == before


def test_group_manager_staff_cannot_read_receipts(pg):
    from apps.accounts.models import Staff

    make_manager(staff_client(superadmin=True), pg)
    s = Staff.objects.get(username="mona")
    assert s.is_group_manager and not s.has_perm("payment.view") and not s.has_perm("agency.view")
    # even if someone gives the staff a powerful role, the group-manager link still restricts it
    s.role = Role.objects.create(name="powerful")
    s.role.permissions.set([Permission.objects.get_or_create(code="payment.view", defaults={"name": "x"})[0]])
    s.save()
    assert not Staff.objects.get(pk=s.pk).has_perm("payment.view")


def test_staff_tokens_do_not_open_the_manager_api(pg):
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    assert boss.get(M + "me/").status_code == 403            # a superadmin is not a group manager
    plain = staff_client(perms=["agency.view", "agency.manage"], name="plain")
    assert plain.get(M + "me/").status_code == 403
    assert APIClient().get(M + "me/").status_code == 401


def test_old_portal_login_is_gone(pg):
    make_manager(staff_client(superadmin=True), pg)
    r = APIClient().post(M + "login/", {"username": "mona", "password": "mgr-Pass-123"}, format="json")
    assert r.status_code == 410 and r.json()["code"] == "moved"
    # an old "Manager <token>" header opens nothing
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION="Manager abc")
    assert c.get(M + "me/").status_code in (401, 403)
    assert c.get("/api/v1/admin/agency/").status_code == 403


def test_staff_username_must_be_free_for_a_new_manager(pg):
    boss = staff_client(superadmin=True)
    staff_client(superadmin=False, name="taken")
    r = boss.post("/api/v1/admin/agency/managers/", {"username": "taken", "password": "mgr-Pass-123",
                                                     "assignments": [{"group_id": pg["g1"].id, "role_ids": [6]}]},
                  format="json")
    assert r.status_code == 409 and r.json()["field"] == "username"


def test_existing_managers_are_converted_to_staff(pg):
    """Migration agency.0007: same username + password hash, role "Group manager"; a taken
    staff username is never linked."""
    import importlib

    from django.apps import apps as live_apps
    from django.contrib.auth.hashers import make_password

    from apps.accounts.models import Staff

    mig = importlib.import_module("apps.agency.migrations.0007_group_manager_staff")
    old = GroupManager.objects.create(username="legacy", password=make_password("Legacy-Pass-1"), display_name="L")
    from apps.agency.models import GroupManagerAssignment

    GroupManagerAssignment.objects.create(manager=old, group=pg["g1"], allowed_role_ids=[6])
    staff_client(name="clash")
    GroupManager.objects.create(username="clash", password=make_password("Clash-Pass-1"))
    mig.forwards(live_apps, None)
    old.refresh_from_db()
    assert old.staff is not None and old.staff.username == "legacy" and old.staff.role.name == "Group manager"
    assert old.staff.check_password("Legacy-Pass-1")
    assert GroupManager.objects.get(username="clash").staff is None
    assert not Staff.objects.get(username="clash").is_group_manager
    mc = manager_client(username="legacy", password="Legacy-Pass-1")
    assert [g["id"] for g in mc.get(M + "me/").json()["groups"]] == [pg["g1"].id]
    mig.forwards(live_apps, None)                                                # idempotent
    assert Staff.objects.filter(username="legacy").count() == 1


# ------------------------------------------------------------------ accounting + group statement
def test_accounting_and_group_statement(pg):
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    ledger.add_entry("g1-a", "payment", 50000, ledger.today(), method="card")
    ledger.add_entry("g2-owner", "manual_charge", 99999, ledger.today())
    mc = manager_client()
    mc.post(M + "admins/g1-a/add-volume/", {"gb": 100}, format="json")
    boss.post(f"/api/v1/admin/agency/approvals/{VolumeRequest.objects.get().id}/approve/", {}, format="json")
    mc.post(M + "admins/g1-owner/add-volume/", {"gb": 10}, format="json")           # stays pending
    acc = mc.get(M + "accounting/").json()["groups"][0]
    rows = {r["username"]: r for r in acc["admins"]}
    assert Decimal(str(rows["g1-a"]["balance"])) == Decimal("150000")              # 200,000 charge − 50,000 paid
    assert Decimal(str(acc["pending_gb"])) == Decimal("10") and Decimal(str(acc["pending_amount"])) == Decimal("20000")
    st = mc.get(M + f"groups/{pg['g1'].id}/statement/").json()
    assert [e["admin"] for e in st["entries"]] == ["g1-a", "g1-a"]                  # g2's entry never shows
    assert Decimal(str(st["entries"][-1]["balance"])) == Decimal("150000") and Decimal(str(st["total_debt"])) == Decimal("150000")
    assert len(st["pending"]) == 1 and st["pending"][0]["admin"] == "g1-owner"
    # staff: any group, Jalali filter, exports
    s2 = boss.get(f"/api/v1/admin/agency/ledger/groups/{pg['g2'].id}/statement/").json()
    assert Decimal(str(s2["total_debt"])) == Decimal("99999")
    future = boss.get(f"/api/v1/admin/agency/ledger/groups/{pg['g1'].id}/statement/?from=1499/01/01").json()
    assert future["entries"] == [] and Decimal(str(future["opening"])) == Decimal("150000")
    csv = boss.get(f"/api/v1/admin/agency/ledger/groups/{pg['g1'].id}/statement/?export=csv&lang=en")
    assert csv.status_code == 200 and "g1-a" in csv.content.decode() and "Pending approval" in csv.content.decode()
    x = mc.get(M + f"groups/{pg['g1'].id}/statement/?export=xlsx")
    assert x.status_code == 200 and x.content[:2] == b"PK"
    assert mc.get(M + "accounting/?export=csv").status_code == 200
    assert mc.get(M + "admins/g1-a/statement/?export=xlsx").content[:2] == b"PK"
    groups = boss.get("/api/v1/admin/agency/ledger/groups/").json()["results"]
    assert {g["name"]: g["managers"] for g in groups}["Team one"] == ["mona"]
    # read-only for staff without accounting
    assert staff_client(perms=["agency.view"], name="v").get(f"/api/v1/admin/agency/ledger/groups/{pg['g1'].id}/statement/").status_code == 403


def test_activity_on_the_group_page(pg):
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    manager_client().post(M + "admins/g1-a/add-volume/", {"gb": 5}, format="json")
    acts = boss.get(f"/api/v1/admin/agency/groups/{pg['g1'].id}/activity/").json()
    assert acts["results"][0]["action"] == "agency.manager.volume_added" and acts["results"][0]["by"] == "manager:mona"
    assert acts["managers"][0]["username"] == "mona"
    assert boss.get(f"/api/v1/admin/agency/groups/{pg['g2'].id}/activity/").json()["results"] == []
