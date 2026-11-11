"""v1.54 — (1) agency admins / group managers are archived, never deleted; (2) «تاریخچه» built from immutable records.

1. An admin gone from PasarGuard (the sync — the one deliberate PAMP deviation, PORTING.md) or deleted in our panel is
   archived: hidden from active lists / sync / enforcement, but its ledger, invoices, payments, limit history, snapshots,
   AdminLimit and group link all stay; it shows under «بایگانی» (staff + group manager); its balance stays payable and in
   the group's debt; back on PasarGuard → restored with its history. A deleted group-manager account → manager deactivated
   + archived, its requests / payments stay, its groups pay directly again.
2. History per period + 12 Jalali months: sales (GB, T) never shrink because of a settlement («کاهش بدهی»), payments or
   adjustments; opening / closing balance; invoiced; new users (from the first-seen log); staff (all / group / admin),
   group manager (own groups only), portal (own only); CSV / Excel.
"""
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, Staff
from apps.adminpanel.tokens import issue_tokens
from apps.agency import billing, history, ledger, tasks
from apps.agency.models import (AdminGroup, AdminLimit, AdminLimitChange, AgencyInvoice, AgencyUserSeen, GroupManager,
                                GroupManagerAssignment, LedgerEntry, PanelAdmin, UserTrafficSnapshot, VolumeRequest)
from apps.common.models import AuditLog
from apps.panel.models import Panel
from apps.settings_app.models import ValueType
from apps.settings_app.utils import set_setting

pytestmark = pytest.mark.django_db
GB = 1024 ** 3


@pytest.fixture(autouse=True)
def setup():
    cache.clear()
    set_setting("agency_sync_enabled", True, ValueType.BOOL)
    set_setting("agency_enforcement_enabled", True, ValueType.BOOL)
    Panel.objects.create(name="sigma", base_url="https://sigma.test", admin_username="u", admin_password_enc="p", is_active=True)


def staff(codes=None, superadmin=False, name="pouya"):
    s = Staff(username=name, is_superadmin=superadmin)
    if codes is not None:
        role = Role.objects.create(name=f"r-{name}")
        role.permissions.set([Permission.objects.get_or_create(code=c, defaults={"name": c})[0] for c in codes])
        s.role = role
    s.set_password("x-Str0ng!"); s.save()
    c = APIClient(); c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    return c, s


def _row(name, limit=100 * GB, users=()):
    return {"username": name, "is_sudo": False, "is_active": True, "status": "active", "has_data_limit": bool(limit),
            "admin_limit_bytes": limit, "admin_remaining": 0, "total_user_used": 150 * GB, "total_user_limit": 0, "user_count": 1,
            "active_user_count": 1, "on_hold_users": 0, "limited_users": 0, "disabled_users": 0, "expired_users": 0,
            "raw_data": {}, "users": [{"username": u, "used_traffic": 0} for u in users],
            "skip_deleted_detection": not users}


def _sync(monkeypatch, rows):
    monkeypatch.setattr("apps.agency.panel_api.PanelAPIClient.sync_all_admins", lambda self: rows)
    monkeypatch.setattr("apps.agency.panel_api.PanelAPIClient.__init__", lambda self: None)
    puts = []
    monkeypatch.setattr("apps.agency.panel_api.PanelAPIClient.disable_admin", lambda self, u: puts.append(("disable", u)) or (True, ""), raising=False)
    monkeypatch.setattr("apps.agency.panel_api.PanelAPIClient.enable_admin", lambda self, u: puts.append(("enable", u)) or (True, ""), raising=False)
    monkeypatch.setattr("apps.agency.panel_api.PanelAPIClient.authenticate", lambda self: True, raising=False)
    tasks._pamp_sync(SimpleNamespace(retry=lambda exc: exc))
    return puts


def _gone_admin():
    """An admin with every kind of record: limit config, snapshot, ledger + invoice, limit history, request, group."""
    a = PanelAdmin.objects.create(username="gone", has_data_limit=True, admin_limit_bytes=100 * GB, total_user_used=150 * GB)
    PanelAdmin.objects.create(username="stay", has_data_limit=True, admin_limit_bytes=100 * GB)
    AdminLimit.objects.create(panel_admin=a, limit_bytes=100 * GB)
    UserTrafficSnapshot.objects.create(panel_admin=a, user_username="u1", used_traffic_bytes=5 * GB)
    ledger.set_price("gone", 1000, ledger.today())
    e = ledger.record_quota_charge("gone", 0, 100 * GB, by="t")
    from apps.agency import limit_history

    limit_history.record("gone", 0, 100 * GB, action="set", source="panel", by="t")
    VolumeRequest.objects.create(admin_username="gone", gb=Decimal(5), kind="request", manager_username="",
                                 old_limit_bytes=100 * GB, new_limit_bytes=105 * GB)
    AdminGroup.objects.create(owner_username="stay", member_usernames="gone")
    return a, e


# ------------------------------------------------------------------ 1. archive, never delete
def test_the_sync_archives_an_admin_gone_from_pasarguard_and_keeps_everything(monkeypatch):
    a, entry = _gone_admin()
    puts = _sync(monkeypatch, [_row("stay")])
    assert not PanelAdmin.objects.filter(username="gone").exists()                   # hidden from active lists
    g = PanelAdmin.all_objects.get(username="gone")
    assert g.archived_at and g.archived_reason == "panel_missing" and g.archived_by == "sync"
    assert AdminLimit.objects.filter(panel_admin=g).exists() and UserTrafficSnapshot.objects.filter(panel_admin=g).exists()
    assert LedgerEntry.objects.filter(admin_username="gone").count() == 1
    assert AgencyInvoice.objects.filter(admin_username="gone").count() == 1
    assert AdminLimitChange.objects.filter(admin_username="gone").exists() and VolumeRequest.objects.filter(admin_username="gone").exists()
    assert "gone" in AdminGroup.objects.get(owner_username="stay").member_usernames
    assert ("disable", "gone") not in puts                                              # enforcement never touches it
    assert AuditLog.objects.filter(action="agency.admin_archived", detail__admin="gone").exists()
    # back on PasarGuard → restored, same row, history continues
    _sync(monkeypatch, [_row("stay"), _row("gone")])
    r = PanelAdmin.objects.get(username="gone")
    assert r.pk == g.pk and r.archived_at is None and AuditLog.objects.filter(action="agency.admin_restored").exists()


def test_an_empty_admin_list_never_archives_anyone(monkeypatch):
    _gone_admin()
    _sync(monkeypatch, [])
    assert PanelAdmin.objects.filter(username="gone").exists()


def test_archived_admins_show_under_the_archive_filter_and_stay_payable(monkeypatch):
    _gone_admin()
    _sync(monkeypatch, [_row("stay")])
    c, _ = staff(superadmin=True)
    active = c.get("/api/v1/admin/agency/admins/").json()
    assert "gone" not in [r["username"] for r in active["results"]] and active["archived_count"] == 1
    arch = c.get("/api/v1/admin/agency/admins/?archived=1").json()["results"]
    assert [r["username"] for r in arch] == ["gone"] and arch[0]["archived"] and arch[0]["archived_reason"] == "panel_missing"
    assert c.get("/api/v1/admin/agency/admins/gone/").json()["archived"] is True            # its page still opens
    r = c.post("/api/v1/admin/agency/admins/gone/set-limit/", {"action": "add", "value_gb": 10}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "archived"                           # nothing on the panel
    # the balance stays payable / adjustable by our staff
    ledger.add_entry("gone", LedgerEntry.KIND_PAYMENT, 40000, ledger.today(), method="card", by="t")
    ledger.add_entry("gone", LedgerEntry.KIND_ADJUST, 10000, ledger.today(), direction="decrease", by="t")
    assert ledger.balances()["gone"] == Decimal(100 * 1000 - 40000 - 10000)
    # and it stays in its group's debt («پرداخت کل بدهی»)
    names = AdminGroup.objects.get(owner_username="stay").get_all_usernames()
    assert "gone" in [r["admin"] for r in billing.debt_breakdown(names)["admins"]]


def test_deleting_in_our_panel_archives_and_creating_the_name_again_restores(monkeypatch):
    from apps.agency import admin_crud as C

    _gone_admin()
    monkeypatch.setattr(C, "_gate", lambda: None)
    monkeypatch.setattr(C.PasarGuardClient, "_request", lambda self, *a, **k: {})
    C.delete(Panel.objects.get(), "gone", "gone", by="pouya")
    g = PanelAdmin.all_objects.get(username="gone")
    assert g.archived_reason == "deleted" and g.archived_by == "pouya"
    assert AdminGroup.objects.filter(owner_username="stay").exists()
    monkeypatch.setattr(C, "get_admin", lambda panel, u: {"username": u})
    C.create(Panel.objects.get(), {"username": "gone", "password": C.generate_password(), "role_id": 3}, by="pouya", charge=False)
    assert PanelAdmin.objects.get(username="gone").pk == g.pk                          # history continues


def test_a_deleted_group_manager_account_is_deactivated_not_deleted():
    gm_staff = Staff(username="imantorabian"); gm_staff.set_password("x-Str0ng!"); gm_staff.save()
    m = GroupManager.objects.create(username="imantorabian", password="x", staff=gm_staff)
    PanelAdmin.objects.create(username="owner1")
    g = AdminGroup.objects.create(owner_username="owner1", member_usernames="")
    GroupManagerAssignment.objects.create(manager=m, group=g)
    VolumeRequest.objects.create(admin_username="owner1", gb=Decimal(1), kind="add", manager=m, manager_username=m.username,
                                 old_limit_bytes=0, new_limit_bytes=GB)
    assert billing.payer_for("owner1") == "manager"
    c, _ = staff(superadmin=True)
    assert c.delete(f"/api/v1/admin/staff/{gm_staff.pk}/").status_code == 204
    m.refresh_from_db(); gm_staff.refresh_from_db()
    assert m.is_active is False and m.archived_at is not None and m.staff_id == gm_staff.pk
    assert gm_staff.is_active is False and GroupManagerAssignment.objects.filter(manager=m).exists()
    assert VolumeRequest.objects.filter(manager=m).exists()
    assert billing.payer_for("owner1") == "admin"                                       # the group pays directly again
    lst = c.get("/api/v1/admin/agency/managers/").json()
    assert lst["results"] == [] and lst["archived_count"] == 1
    assert [r["username"] for r in c.get("/api/v1/admin/agency/managers/?archived=1").json()["results"]] == ["imantorabian"]


# ------------------------------------------------------------------ 2. history
def _day(n):
    return ledger.today() - timedelta(days=n)


def test_gross_charges_stay_and_net_sales_follow_the_adjustments():
    PanelAdmin.objects.create(username="farz")
    ledger.set_price("farz", 2000, _day(40))
    ledger.record_quota_charge("farz", 0, 100 * GB, by="t", day=_day(2))                 # 200,000 T, 100 GB
    before = history.summary(["farz"], *history.bounds("d7"))
    ledger.add_entry("farz", LedgerEntry.KIND_ADJUST, 150000, _day(1), direction="decrease", by="t")   # «کاهش بدهی»
    ledger.add_entry("farz", LedgerEntry.KIND_PAYMENT, 50000, _day(0), method="card", by="t")
    after = history.summary(["farz"], *history.bounds("d7"))
    assert (before["gb"], before["charged"]) == (after["gb"], after["charged"]) == (Decimal(100), Decimal(200000))
    assert after["adjustments"] == Decimal(-150000) and after["paid"] == Decimal(50000) and after["closing"] == Decimal(0)
    # v1.54.1: net sales = gross charges ∓ adjustments («کاهش بدهی» lowers it, «افزایش بدهی» raises it), in their period
    assert before["net_sales"] == Decimal(200000) and after["net_sales"] == Decimal(50000)
    ledger.add_entry("farz", LedgerEntry.KIND_ADJUST, 30000, _day(0), direction="increase", by="t")
    assert history.summary(["farz"], *history.bounds("d7"))["net_sales"] == Decimal(80000)
    old = history.summary(["farz"], _day(400), _day(3))                                    # before the adjustments: untouched
    assert old["charged"] == old["net_sales"] == Decimal(0)
    assert after["invoiced"] == Decimal(200000)
    # the agency reports too: «شارژ» no longer shrinks, adjustments are apart
    from apps.agency import reports

    k = reports.overview(_day(6), _day(0))["kpis"]
    assert k["charges"] == 200000 and k["adjustments"] == -120000 and k["net_sales"] == 80000 and k["net"] == 30000
    m = [r for r in reports.monthly() if r["charges"]][0]
    assert m["net_sales"] == m["charges"] + m["adjustments"]
    rows = history.export_rows(history.report(["farz"], "d7"), "fa")
    assert "فروش خالص (تومان)" in rows[0] and "شارژ ناخالص (تومان)" in rows[0]


def test_periods_monthly_table_opening_closing_and_new_users(monkeypatch):
    PanelAdmin.objects.create(username="amir")
    ledger.set_price("amir", 1000, _day(400))
    ledger.record_quota_charge("amir", 0, 10 * GB, by="t", day=_day(45))
    ledger.record_quota_charge("amir", 10 * GB, 30 * GB, by="t", day=_day(1))
    ledger.add_entry("amir", LedgerEntry.KIND_PAYMENT, 5000, _day(1), method="card", by="t")
    s = history.summary(["amir"], *history.bounds("d7"))
    assert s["opening"] == Decimal(10000) and s["charged"] == Decimal(20000) and s["closing"] == Decimal(25000)
    rows = history.monthly(["amir"])
    assert len(rows) == 12 and rows[0]["to"] == ledger.today()
    assert sum((r["charged"] for r in rows), Decimal(0)) == Decimal(30000)
    a, b = history.bounds("custom", _day(50).isoformat(), _day(0).isoformat())
    assert history.summary(["amir"], a, b)["charged"] == Decimal(30000)
    with pytest.raises(history.HistoryError):
        history.bounds("custom", _day(0).isoformat(), _day(5).isoformat())
    # new users: unknown before the first-seen log exists, counted after — and they stay counted after deletion
    assert s["new_users"] is None
    PanelAdmin.objects.filter(username="amir").update(has_data_limit=False)
    _sync(monkeypatch, [_row("amir", 0, users=("u1", "u2"))])
    _sync(monkeypatch, [_row("amir", 0, users=("u2", "u3"))])                           # u1 deleted, u3 new
    assert AgencyUserSeen.objects.filter(admin_username="amir").count() == 3
    assert history.summary(["amir"], *history.bounds("d7"))["new_users"] == 3


def test_staff_manager_and_portal_scopes_and_exports():
    for n in ("o1", "m1", "x1"):
        PanelAdmin.objects.create(username=n)
        ledger.set_price(n, 1000, _day(10))
        ledger.record_quota_charge(n, 0, 10 * GB, by="t", day=_day(1))
    g = AdminGroup.objects.create(owner_username="o1", member_usernames="m1")
    c, _ = staff(["agency.accounting"], name="acc")
    r = c.get("/api/v1/admin/agency/history/?period=d7").json()
    assert r["totals"]["charged"] == "30000" or Decimal(str(r["totals"]["charged"])) == Decimal(30000)
    r = c.get(f"/api/v1/admin/agency/history/?scope=group&group={g.id}&period=d7").json()
    assert Decimal(str(r["totals"]["charged"])) == Decimal(20000) and {x["username"] for x in r["admins"]} == {"o1", "m1"}
    x = c.get("/api/v1/admin/agency/history/?admin=x1&period=month&export=csv")
    assert x.status_code == 200 and "text/csv" in x["Content-Type"]
    assert c.get("/api/v1/admin/agency/history/?admin=x1&export=xlsx").status_code == 200
    assert c.get("/api/v1/admin/agency/history/?period=custom&from=bad").status_code == 400
    c2, _ = staff(["agency.view"], name="viewer")
    assert c2.get("/api/v1/admin/agency/history/").status_code == 403                      # accounting data
    # group manager: own groups only
    gm_staff = Staff(username="gm1"); gm_staff.set_password("x-Str0ng!")
    gm_role = Role.objects.create(name="Group manager")
    gm_role.permissions.set([Permission.objects.get_or_create(code=c_, defaults={"name": c_})[0]
                             for c_ in ("agency.group_manager", "agency.gm.accounting")])
    gm_staff.role = gm_role; gm_staff.save()
    m = GroupManager.objects.create(username="gm1", password="x", staff=gm_staff)
    GroupManagerAssignment.objects.create(manager=m, group=g)
    mc = APIClient(); mc.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(gm_staff)['access']}")
    r = mc.get("/api/v1/agency/manager/history/?period=d7")
    assert r.status_code == 200, r.content
    assert Decimal(str(r.json()["totals"]["charged"])) == Decimal(20000)
    assert mc.get("/api/v1/agency/manager/history/?admin=x1").status_code == 403
    assert mc.get(f"/api/v1/agency/manager/history/?group={g.id}&export=csv").status_code == 200
    # portal: own account only
    import secrets as _s

    from django.utils import timezone

    from apps.agency import portal
    from apps.agency.models import ResellerSession

    set_setting("agency_portal_enabled", True, ValueType.BOOL)
    tok = _s.token_urlsafe(32)
    ResellerSession.objects.create(username="x1", key_hash=portal._hash(tok), expires_at=timezone.now() + timedelta(hours=1))
    pc = APIClient(); pc.credentials(HTTP_AUTHORIZATION=f"Agency {tok}")
    r = pc.get("/api/v1/agency/portal/history/?period=d7")
    assert r.status_code == 200, r.content
    assert Decimal(str(r.json()["totals"]["charged"])) == Decimal(10000) and r.json()["admins"] == []
    assert pc.get("/api/v1/agency/portal/history/?admin=o1").status_code == 403
    assert pc.get("/api/v1/agency/portal/history/?export=csv").status_code == 200
