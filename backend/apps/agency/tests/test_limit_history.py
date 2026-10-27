"""Admin limit history: every data-limit change is recorded with old → new, who and
where — our agency panel (set / add / remove / create) and PasarGuard directly
(detected by the sync) — plus an `agency.limit_changed` audit entry, shown in the
admin's "Limit history" tab. Includes the 2026-10-27 case: a limit set to 1 TB
instead of +1000 GB, then removed."""
from decimal import Decimal
from types import SimpleNamespace

import pytest
import responses
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import Staff
from apps.adminpanel.tokens import issue_tokens
from apps.agency import ledger, tasks
from apps.agency.models import AdminLimitChange, LedgerEntry, PanelAdmin
from apps.common.models import AuditLog
from apps.panel.models import Panel
from apps.settings_app.models import ValueType
from apps.settings_app.utils import set_setting

pytestmark = pytest.mark.django_db
GB = 1024 ** 3
BASE = "https://sigma.test"
BEFORE = 27_830 * GB            # Mostafa-ho's limit before the mistake (29,882,234,961,920 bytes)


@pytest.fixture(autouse=True)
def setup():
    cache.clear()
    set_setting("agency_sync_enabled", True, ValueType.BOOL)
    Panel.objects.create(name="sigma", base_url=BASE, admin_username="u", admin_password_enc="p", is_active=True)
    PanelAdmin.objects.create(username="Mostafa-ho", has_data_limit=True, admin_limit_bytes=BEFORE, last_limit_bytes=BEFORE,
                              admin_remaining=233 * GB, total_user_used=27_597 * GB)
    ledger.set_price("Mostafa-ho", 2000, ledger.today())


def boss():
    s = Staff(username="pouya", is_superadmin=True)
    s.set_password("x-Str0ng!"); s.save()
    c = APIClient(); c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    return c


def panel_ok():
    responses.add("POST", f"{BASE}/api/admin/token", json={"access_token": "t"})
    responses.add("PUT", f"{BASE}/api/admin/Mostafa-ho", json={})


@responses.activate
def test_set_by_mistake_then_removed_is_fully_traced_without_charges():
    panel_ok()
    c = boss()
    url = "/api/v1/admin/agency/admins/Mostafa-ho/"
    assert c.post(url + "set-limit/", {"action": "set", "value_gb": 1000}, format="json").status_code == 200
    assert c.post(url + "remove-limit/", {}, format="json").status_code == 200
    rows = c.get(url + "limit-history/").json()["results"]
    assert [(r["action"], r["source"], r["staff"]) for r in rows] == [("remove", "panel", "pouya"), ("set", "panel", "pouya")]
    rem, setr = rows
    assert (setr["old_limit_bytes"], setr["new_limit_bytes"]) == (BEFORE, 1000 * GB)
    assert setr["delta_bytes"] == 1000 * GB - BEFORE and setr["ledger"] is None and "27,830.0 GB" in setr["old_fmt"]
    assert (rem["old_limit_bytes"], rem["new_limit_bytes"]) == (1000 * GB, 0) and rem["new_fmt"] == "Unlimited"
    assert not LedgerEntry.objects.exists()                    # a decrease and a removal never charge
    logs = AuditLog.objects.filter(action="agency.limit_changed").order_by("id")
    assert [(l.detail["action"], l.detail["old_limit_bytes"], l.detail["new_limit_bytes"], l.staff_label) for l in logs] == [
        ("set", BEFORE, 1000 * GB, "pouya"), ("remove", 1000 * GB, 0, "pouya")]
    assert logs[0].detail["source"] == "panel"


@responses.activate
def test_the_intended_increase_charges_exactly_1000_gb_and_links_the_entry():
    panel_ok()
    c = boss()
    r = c.post("/api/v1/admin/agency/admins/Mostafa-ho/set-limit/", {"action": "add", "value_gb": 1000}, format="json")
    assert r.status_code == 200
    e = LedgerEntry.objects.get()
    assert (e.gb, e.amount, e.old_limit_bytes, e.new_limit_bytes) == (Decimal("1000.0000"), Decimal("2000000"), BEFORE, 28_830 * GB)
    h = AdminLimitChange.objects.get()
    assert h.ledger_entry == e and h.action == "add" and h.new_limit_bytes == 28_830 * GB


def _sync_row(limit_bytes):
    return {"username": "Mostafa-ho", "is_sudo": False, "is_active": True, "status": "active",
            "has_data_limit": bool(limit_bytes), "admin_limit_bytes": limit_bytes, "admin_remaining": 0,
            "total_user_used": 27_597 * GB, "total_user_limit": 0, "user_count": 1, "active_user_count": 1,
            "on_hold_users": 0, "limited_users": 0, "disabled_users": 0, "expired_users": 0, "raw_data": {},
            "users": [], "skip_deleted_detection": True}


def test_sync_detects_a_change_made_directly_on_pasarguard(monkeypatch):
    rows = {"v": [_sync_row(BEFORE)]}
    monkeypatch.setattr("apps.agency.panel_api.PanelAPIClient.sync_all_admins", lambda self: rows["v"])
    monkeypatch.setattr("apps.agency.panel_api.PanelAPIClient.__init__", lambda self: None)
    me = SimpleNamespace(retry=lambda exc: exc)
    tasks._pamp_sync(me)
    assert not AdminLimitChange.objects.exists()               # unchanged → nothing recorded
    rows["v"] = [_sync_row(5000 * GB)]
    tasks._pamp_sync(me)
    rows["v"] = [_sync_row(0)]                                 # removed on PasarGuard
    tasks._pamp_sync(me)
    hist = list(AdminLimitChange.objects.order_by("id").values_list("action", "source", "old_limit_bytes", "new_limit_bytes", "staff"))
    assert hist == [("external", "pasarguard", BEFORE, 5000 * GB, ""), ("external", "pasarguard", 5000 * GB, 0, "")]
    log = AuditLog.objects.filter(action="agency.limit_changed").first()
    assert log.detail["source"] == "pasarguard" and "directly on PasarGuard" in log.detail["note"]


@responses.activate
def test_our_own_change_is_not_reported_again_by_the_next_sync(monkeypatch):
    panel_ok()
    boss().post("/api/v1/admin/agency/admins/Mostafa-ho/set-limit/", {"action": "add", "value_gb": 10}, format="json")
    monkeypatch.setattr("apps.agency.panel_api.PanelAPIClient.sync_all_admins", lambda self: [_sync_row(BEFORE + 10 * GB)])
    monkeypatch.setattr("apps.agency.panel_api.PanelAPIClient.__init__", lambda self: None)
    tasks._pamp_sync(SimpleNamespace(retry=lambda exc: exc))
    assert list(AdminLimitChange.objects.values_list("action", flat=True)) == ["add"]


def test_history_needs_the_view_permission():
    c = APIClient()
    assert c.get("/api/v1/admin/agency/admins/Mostafa-ho/limit-history/").status_code == 401


# ------------------------------------------------------------------ unlimited admins: the last finite limit is the base
def _remove_then(c, payload):
    url = "/api/v1/admin/agency/admins/Mostafa-ho/"
    assert c.post(url + "remove-limit/", {}, format="json").status_code == 200
    a = PanelAdmin.objects.get(username="Mostafa-ho")
    assert (a.has_data_limit, a.admin_limit_bytes, a.last_limit_bytes) == (False, 0, BEFORE)   # remembered
    prev = c.post(url + "set-limit/preview/", payload, format="json").json()
    r = c.post(url + "set-limit/", payload, format="json")
    assert r.status_code == 200, r.json()
    return prev, PanelAdmin.objects.get(username="Mostafa-ho")


@responses.activate
def test_add_from_unlimited_starts_from_the_last_limit_and_charges_only_x():
    panel_ok()
    prev, a = _remove_then(boss(), {"action": "add", "value_gb": 1000})
    assert prev["unlimited_now"] is True and prev["base_limit_bytes"] == BEFORE and prev["old_limit_bytes"] == 0
    assert prev["new_limit_bytes"] == 28_830 * GB and float(prev["charge"]["gb"]) == 1000 and float(prev["charge"]["amount"]) == 2_000_000
    assert a.admin_limit_bytes == 28_830 * GB and a.last_limit_bytes == 28_830 * GB
    e = LedgerEntry.objects.get()
    assert (e.gb, e.amount, e.old_limit_bytes, e.new_limit_bytes) == (Decimal("1000.0000"), Decimal("2000000"), BEFORE, 28_830 * GB)
    h = AdminLimitChange.objects.filter(action="add").get()
    assert h.old_limit_bytes == 0 and "last limit" in h.note and h.ledger_entry == e


@responses.activate
def test_set_from_unlimited_charges_only_the_difference_to_the_last_limit():
    panel_ok()
    prev, a = _remove_then(boss(), {"action": "set", "value_gb": 28_830})
    assert prev["base_limit_bytes"] == BEFORE and float(prev["charge"]["gb"]) == 1000
    e = LedgerEntry.objects.get()
    assert e.amount == Decimal("2000000") and e.old_limit_bytes == BEFORE        # not 28,830 GB × 2000 = 57,660,000


@responses.activate
def test_set_below_the_last_limit_from_unlimited_charges_nothing():
    panel_ok()
    prev, a = _remove_then(boss(), {"action": "set", "value_gb": 1000})
    assert prev["charge"] is None and a.admin_limit_bytes == 1000 * GB and not LedgerEntry.objects.exists()


@responses.activate
def test_never_limited_admin_still_charges_the_whole_limit():
    panel_ok()
    PanelAdmin.objects.filter(username="Mostafa-ho").update(has_data_limit=False, admin_limit_bytes=0, last_limit_bytes=0)
    c = boss()
    prev = c.post("/api/v1/admin/agency/admins/Mostafa-ho/set-limit/preview/", {"action": "add", "value_gb": 10}, format="json").json()
    assert prev["unlimited_now"] is True and prev["base_limit_bytes"] == 0 and float(prev["charge"]["gb"]) == 10


def test_sync_keeps_the_last_finite_limit_through_unlimited(monkeypatch):
    rows = {"v": [_sync_row(26_000 * GB)]}
    monkeypatch.setattr("apps.agency.panel_api.PanelAPIClient.sync_all_admins", lambda self: rows["v"])
    monkeypatch.setattr("apps.agency.panel_api.PanelAPIClient.__init__", lambda self: None)
    me = SimpleNamespace(retry=lambda exc: exc)
    tasks._pamp_sync(me)
    assert PanelAdmin.objects.get(username="Mostafa-ho").last_limit_bytes == 26_000 * GB
    rows["v"] = [_sync_row(0)]
    tasks._pamp_sync(me)
    a = PanelAdmin.objects.get(username="Mostafa-ho")
    assert (a.has_data_limit, a.last_limit_bytes) == (False, 26_000 * GB)
