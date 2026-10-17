"""Phase 3 + 4: reseller portal (panel-verified login, own session, own numbers
only) and the accounting ledger (quota charges, prices with history, payments,
balance, statement, export) — additive, never touching PAMP's numbers."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
import responses
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, Staff, User
from apps.adminpanel.tokens import issue_tokens
from apps.agency import ledger
from apps.agency.enrich import _enrich, portal_state
from apps.agency.models import AdminGroup, LedgerEntry, PanelAdmin, ResellerSession
from apps.panel.models import Panel
from apps.settings_app.models import ValueType
from apps.settings_app.utils import set_setting

pytestmark = pytest.mark.django_db
GB = 1024 ** 3
BASE = "https://sigma.test"


@pytest.fixture(autouse=True)
def setup():
    cache.clear()
    Panel.objects.create(name="sigma", base_url=BASE, admin_username="u", admin_password_enc="p", is_active=True)
    PanelAdmin.objects.create(username="ali", has_data_limit=True, admin_limit_bytes=100 * GB, admin_remaining=10 * GB,
                              total_user_limit=120 * GB, total_user_used=90 * GB, deleted_users_used_bytes=3 * GB)
    PanelAdmin.objects.create(username="bea", total_user_limit=5 * GB, total_user_used=7 * GB, pamp_blocked=True)
    PanelAdmin.objects.create(username="cyrus", has_data_limit=True, admin_limit_bytes=GB)
    AdminGroup.objects.create(owner_username="bea", member_usernames="cyrus")


def staff(perms=None, superadmin=False, name="s"):
    s = Staff(username=name, is_superadmin=superadmin)
    if perms is not None:
        role = Role.objects.create(name=f"r-{name}")
        role.permissions.set([Permission.objects.get_or_create(code=c, defaults={"name": c})[0] for c in perms])
        s.role = role
    s.set_password("x-Str0ng!"); s.save()
    c = APIClient(); c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    return c


# ------------------------------------------------------------------ ledger
def test_quota_charge_uses_the_price_valid_on_the_day():
    today = ledger.today()
    ledger.set_price("ali", 1000, today - timedelta(days=10))
    ledger.set_price("ali", 1500, today)                       # new price applies from today
    ledger.set_price("ali", 9999, today + timedelta(days=1))   # future price: not yet
    e = ledger.record_quota_charge("ali", 100 * GB, 150 * GB + GB // 2)    # +50.5 GB
    assert e.kind == "quota_charge" and e.price_per_gb == 1500 and e.amount == Decimal("75750")
    assert e.gb == Decimal("50.5000") and e.old_limit_bytes == 100 * GB


def test_amount_rounds_half_up_and_unlimited_counts_as_zero():
    ledger.set_price("ali", 333, ledger.today())
    e = ledger.record_quota_charge("ali", 0, GB // 2 + GB // 4)        # unlimited -> 0.75 GB: 249.75 -> 250
    assert e.amount == Decimal("250")


def test_no_charge_for_a_decrease_or_removal_and_missing_price_is_still_recorded():
    assert ledger.record_quota_charge("ali", 100 * GB, 50 * GB) is None
    assert ledger.record_quota_charge("ali", 100 * GB, 0) is None
    e = ledger.record_quota_charge("cyrus", GB, 3 * GB)
    assert e.amount == 0 and "no price" in e.note


def test_balance_statement_void_and_csv():
    d0 = date(2026, 10, 1)
    ledger.add_entry("ali", "manual_charge", 500000, d0, note="setup")
    ledger.add_entry("ali", "adjustment", -20000, d0 + timedelta(days=1))
    p = ledger.add_entry("ali", "payment", 300000, d0 + timedelta(days=2), method="card")
    bad = ledger.add_entry("ali", "payment", 99999, d0 + timedelta(days=3), method="cash")
    ledger.void(bad.id, "typo", "boss")
    st = ledger.statement("ali")
    assert st["charges"] == Decimal("480000") and st["payments"] == Decimal("300000") and st["balance"] == Decimal("180000")
    assert [r["balance"] for r in st["entries"]] == [500000, 480000, 180000, 180000]
    assert ledger.balances()["ali"] == Decimal("180000")
    csv = ledger.statement_csv("ali")
    assert "1405/07/09" in csv and "voided: typo (boss)" in csv and "balance,180000" in csv
    with pytest.raises(ValueError):
        ledger.add_entry("ali", "payment", 0, d0, method="card")
    with pytest.raises(ValueError):
        ledger.add_entry("ali", "payment", 10, d0, method="bitcoin-atm")
    with pytest.raises(ValueError):
        ledger.void(p.id, "")


@responses.activate
def test_raising_a_limit_through_the_panel_creates_the_charge_after_cutover():
    set_setting("agency_sync_enabled", True, ValueType.BOOL)
    ledger.set_price("ali", 2000, ledger.today())
    responses.add("POST", f"{BASE}/api/admin/token", json={"access_token": "t"})
    responses.add("PUT", f"{BASE}/api/admin/ali", json={})
    c = staff(superadmin=True, name="boss")
    before = _enrich(PanelAdmin.objects.get(username="ali"))
    r = c.post("/api/v1/admin/agency/admins/ali/set-limit/", {"action": "add", "value_gb": 25}, format="json")
    assert r.status_code == 200
    e = LedgerEntry.objects.get()
    assert e.amount == Decimal("50000") and e.created_by == "boss"
    # PAMP's own numbers are exactly what PAMP's set_limit makes them — the ledger adds nothing
    a = PanelAdmin.objects.get(username="ali")
    assert a.admin_limit_bytes == 125 * GB and a.total_user_limit == 120 * GB and a.deleted_users_used_bytes == 3 * GB
    assert _enrich(a)["deleted_used_fmt"] == before["deleted_used_fmt"]


def test_before_cutover_no_charge_can_be_created_through_limits():
    c = staff(superadmin=True)
    assert c.post("/api/v1/admin/agency/admins/ali/set-limit/", {"action": "add", "value_gb": 5}, format="json").status_code == 409
    assert not LedgerEntry.objects.exists()


def test_accounting_api_and_permissions():
    acc = staff(["agency.view", "agency.accounting"], name="acc")
    viewer = staff(["agency.view"], name="viewer")
    assert viewer.get("/api/v1/admin/agency/ledger/").status_code == 403
    assert "balance" not in viewer.get("/api/v1/admin/agency/admins/").json()["results"][0]
    assert acc.post("/api/v1/admin/agency/ledger/ali/prices/", {"price_per_gb": 1200, "valid_from": "2026-10-01"},
                    format="json").status_code == 201
    r = acc.post("/api/v1/admin/agency/ledger/ali/entries/", {"kind": "payment", "amount": 100000, "date": "2026-10-05",
                                                              "method": "card", "note": "Oct"}, format="json")
    assert r.status_code == 201 and r.json()["balance"] == -100000
    assert acc.post("/api/v1/admin/agency/ledger/ali/entries/", {"kind": "payment", "amount": "abc", "method": "card"},
                    format="json").status_code == 400
    assert acc.post("/api/v1/admin/agency/ledger/ali/entries/", {"kind": "quota_charge", "amount": 5},
                    format="json").status_code == 400                      # automatic only
    rows = {r["username"]: r for r in acc.get("/api/v1/admin/agency/admins/").json()["results"]}
    assert rows["ali"]["balance"] == -100000 and rows["bea"]["balance"] == 0
    eid = LedgerEntry.objects.get().id
    assert acc.post(f"/api/v1/admin/agency/ledger/entries/{eid}/void/", {"reason": "dup"}, format="json").json()["balance"] == 0
    resp = acc.get("/api/v1/admin/agency/ledger/ali/export.csv")
    assert resp.status_code == 200 and resp["Content-Type"].startswith("text/csv") and b"1405/07/13" in resp.content
    ov = acc.get("/api/v1/admin/agency/ledger/").json()
    assert {r["username"] for r in ov["results"]} >= {"ali", "bea", "cyrus"}


# ------------------------------------------------------------------ portal
def portal_login(username="ali", password="pw", ok=True, status=200):
    with responses.RequestsMock() as rsps:
        rsps.add("POST", f"{BASE}/api/admin/token", json={"access_token": "x"} if ok else {"detail": "no"},
                 status=200 if ok else 401)
        r = APIClient().post("/api/v1/agency/portal/login/", {"username": username, "password": password}, format="json")
        if status == 200 and ok:
            body = rsps.calls[0].request.body
            assert f"username={username}" in body and "password=pw" in body      # PAMP: form login to the panel
    assert r.status_code == status, r.content
    return r


def reseller(token):
    c = APIClient(); c.credentials(HTTP_AUTHORIZATION=f"Agency {token}")
    return c


def test_portal_is_closed_until_opened():
    r = APIClient().post("/api/v1/agency/portal/login/", {"username": "ali", "password": "pw"}, format="json")
    assert r.status_code == 403 and r.json()["code"] == "portal_closed"


def test_login_is_checked_by_the_panel_and_is_its_own_session():
    set_setting("agency_portal_enabled", True, ValueType.BOOL)
    users_before = User.objects.count()
    token = portal_login().json()["token"]
    s = ResellerSession.objects.get()
    assert s.username == "ali" and s.key_hash != token and len(s.key_hash) == 64
    assert User.objects.count() == users_before and not Staff.objects.filter(username="ali").exists()
    me = reseller(token).get("/api/v1/agency/portal/me/").json()
    a = PanelAdmin.objects.get(username="ali")
    acc = me["accounts"][0]
    assert me["mode"] == "single" and len(me["accounts"]) == 1
    assert acc["sold_limit_fmt"] == _enrich(a)["sold_limit_fmt"] and acc["portal"] == portal_state(a)
    # the reseller token opens nothing else
    assert reseller(token).get("/api/v1/admin/agency/").status_code in (401, 403)
    assert reseller(token).get("/api/v1/auth/me/").status_code in (401, 403)
    assert reseller(token).get("/api/v1/agency/portal/statement/?admin=bea").status_code == 403
    assert reseller(token).post("/api/v1/agency/portal/logout/").status_code == 204
    assert reseller(token).get("/api/v1/agency/portal/me/").status_code == 401


def test_wrong_password_and_username_lockout():
    set_setting("agency_portal_enabled", True, ValueType.BOOL)
    for _ in range(5):
        portal_login(ok=False, status=400)
    r = APIClient().post("/api/v1/agency/portal/login/", {"username": "ali", "password": "pw"}, format="json")
    assert r.status_code == 429                                     # locked without even asking the panel
    assert not ResellerSession.objects.exists()


def test_group_owner_sees_the_group_and_its_statements_blocked_state_kept():
    set_setting("agency_portal_enabled", True, ValueType.BOOL)
    ledger.add_entry("cyrus", "manual_charge", 7000, date(2026, 10, 1))
    token = portal_login("bea").json()["token"]
    me = reseller(token).get("/api/v1/agency/portal/me/").json()
    assert me["mode"] == "group" and [a["username"] for a in me["accounts"]] == ["bea", "cyrus"]
    assert me["accounts"][0]["portal"]["is_blocked"] is True and me["accounts"][0]["portal"]["block_reason"] == "pamp_limited"
    assert me["balances"] == {"bea": 0, "cyrus": 7000}
    st = reseller(token).get("/api/v1/agency/portal/statement/?admin=cyrus").json()
    assert st["balance"] == 7000 and "created_by" not in st["entries"][0] and st["prices"] == []
    assert reseller(token).get("/api/v1/agency/portal/statement/?admin=ali").status_code == 403


def test_unknown_admin_gets_not_found_and_expired_sessions_fail():
    set_setting("agency_portal_enabled", True, ValueType.BOOL)
    token = portal_login("ghost").json()["token"]
    assert reseller(token).get("/api/v1/agency/portal/me/").json()["mode"] == "not_found"
    ResellerSession.objects.update(expires_at=ResellerSession.objects.get().created_at - timedelta(seconds=1))
    assert reseller(token).get("/api/v1/agency/portal/me/").status_code == 401


def test_login_then_data_loads_with_production_throttles(settings):
    """Regression: the test settings switch DRF throttles off, which hid a 500 on every
    authenticated portal request in production (UserRateThrottle read request.user.pk)."""
    from config.settings.base import REST_FRAMEWORK as PROD
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": PROD["DEFAULT_THROTTLE_CLASSES"]}
    set_setting("agency_portal_enabled", True, ValueType.BOOL)
    token = portal_login().json()["token"]
    c = reseller(token)
    me = c.get("/api/v1/agency/portal/me/")
    assert me.status_code == 200 and me.json()["accounts"][0]["username"] == "ali"
    assert c.get("/api/v1/agency/portal/statement/?admin=ali").status_code == 200
    assert c.post("/api/v1/agency/portal/logout/").status_code == 204
    assert c.get("/api/v1/agency/portal/me/").status_code == 401
