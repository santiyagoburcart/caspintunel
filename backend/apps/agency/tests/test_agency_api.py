"""Agency admin API: numbers straight from the ported backend, permissions,
and every write refused until the cut-over (no panel call made)."""
import pytest
import responses
from rest_framework.test import APIClient

from apps.accounts.models import Staff
from apps.adminpanel.tokens import issue_tokens
from apps.agency.enrich import _enrich, dashboard_numbers
from apps.agency.models import AdminGroup, PanelAdmin, SyncLog, UserTrafficSnapshot
from apps.panel.models import Panel
from apps.settings_app.models import ValueType
from apps.settings_app.utils import get_setting, set_setting

pytestmark = pytest.mark.django_db
GB = 1024 ** 3
BASE = "https://sigma.test"


def client(**kw):
    s = Staff(username=kw.pop("username", "boss"), **kw); s.set_password("x-Str0ng!"); s.save()
    c = APIClient(); c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    return c


@pytest.fixture
def data():
    Panel.objects.create(name="sigma", base_url=BASE, admin_username="u", admin_password_enc="p", is_active=True)
    a = PanelAdmin.objects.create(username="ali", has_data_limit=True, admin_limit_bytes=100 * GB,
                                  admin_remaining=10 * GB, total_user_limit=120 * GB, total_user_used=90 * GB,
                                  deleted_users_used_bytes=3 * GB, user_count=4, active_user_count=3)
    PanelAdmin.objects.create(username="bea", total_user_limit=5 * GB, total_user_used=7 * GB)
    PanelAdmin.objects.create(username="cyrus", status="disabled", has_data_limit=True, admin_limit_bytes=GB,
                              pamp_blocked=True)
    UserTrafficSnapshot.objects.create(panel_admin=a, user_username="u1", used_traffic_bytes=2 * GB)
    AdminGroup.objects.create(owner_username="ali", member_usernames="bea")
    SyncLog.objects.create(status="success", admins_synced=3)
    return a


def test_dashboard_numbers_come_from_the_ported_code(data):
    d = client(is_superadmin=True).get("/api/v1/admin/agency/").json()
    ref = dashboard_numbers()
    assert d["total_sold_fmt"] == ref["total_limit_fmt"] and d["total_hidden_fmt"] == ref["total_hidden_fmt"]
    assert d["admin_count"] == 3 and d["near_limit_count"] == ref["near_limit_count"]
    assert [o["username"] for o in d["over_limit"]] == [o["username"] for o in ref["over_limit_admins"]]
    assert d["switches"] == {"sync_enabled": False, "enforcement_enabled": False, "sync_interval_minutes": 15,
                             "writes_enabled": False}


def test_admin_list_and_detail_carry_enrich_values_unchanged(data):
    c = client(is_superadmin=True)
    rows = {r["username"]: r for r in c.get("/api/v1/admin/agency/admins/").json()["results"]}
    e = _enrich(data)
    assert rows["ali"]["sold_limit_fmt"] == e["sold_limit_fmt"] and rows["ali"]["hidden_fmt"] == e["hidden_traffic_fmt"]
    assert rows["ali"]["total_sold_fmt"] == data.total_user_limit_fmt and rows["ali"]["usage_percent"] == data.usage_percent
    assert rows["bea"]["groups"] == [{"id": AdminGroup.objects.get().id, "owner": "ali"}]
    assert rows["cyrus"]["status_code"] == "panel_disabled"
    d = c.get("/api/v1/admin/agency/admins/ali/").json()
    assert d["deleted_used_fmt"] == e["deleted_used_fmt"] and d["snapshots"]["count"] == 1
    assert d["portal"]["show_warning"] is True and d["portal"]["warning_pct"] == 90.0
    assert c.get("/api/v1/admin/agency/admins/nobody/").status_code == 404


def test_filters(data):
    c = client(is_superadmin=True)
    names = lambda q: [r["username"] for r in c.get(f"/api/v1/admin/agency/admins/?{q}").json()["results"]]
    assert names("search=ea") == ["bea"]
    assert names("limit=unlimited") == ["bea"] and set(names("limit=limited")) == {"ali", "cyrus"}
    assert names("status=panel_disabled") == ["cyrus"]
    assert names(f"group={AdminGroup.objects.get().id}") == ["ali", "bea"]


def test_every_write_is_refused_before_the_cutover_without_touching_the_panel(data):
    c = client(is_superadmin=True)
    with responses.RequestsMock() as rsps:                         # any HTTP call would fail
        for path, body in [("ali/set-limit/", {"action": "set", "value_gb": 5}), ("ali/remove-limit/", {}),
                           ("ali/admin-action/", {"action": "disable_admin"}), ("ali/reset-deleted-traffic/", {})]:
            r = c.post(f"/api/v1/admin/agency/admins/{path}", body, format="json")
            assert r.status_code == 409 and r.json()["code"] == "pre_cutover"
        assert c.post("/api/v1/admin/agency/sync-now/").status_code == 409
        assert c.post("/api/v1/admin/agency/groups/", {"owner": "x"}, format="json").status_code == 409
        assert len(rsps.calls) == 0
    data.refresh_from_db()
    assert data.deleted_users_used_bytes == 3 * GB and data.admin_limit_bytes == 100 * GB


@responses.activate
def test_after_cutover_set_limit_follows_pamp(data):
    set_setting("agency_sync_enabled", True, ValueType.BOOL)
    responses.add("POST", f"{BASE}/api/admin/token", json={"access_token": "t"})
    responses.add("PUT", f"{BASE}/api/admin/ali", json={})
    r = client(is_superadmin=True).post("/api/v1/admin/agency/admins/ali/set-limit/",
                                        {"action": "add", "value_gb": 50}, format="json")
    assert r.status_code == 200 and r.json()["message"].startswith("Limit set to 150 GB")
    data.refresh_from_db()
    assert data.admin_limit_bytes == 150 * GB and data.admin_remaining == 150 * GB - 90 * GB


def test_permissions(data):
    assert client(username="n").get("/api/v1/admin/agency/").status_code == 403
    from apps.accounts.models import Permission, Role

    viewer = Role.objects.create(name="viewer")
    viewer.permissions.set([Permission.objects.get_or_create(code="agency.view", defaults={"name": "v"})[0]])
    c = client(username="v", role=viewer)
    assert c.get("/api/v1/admin/agency/admins/").status_code == 200
    assert c.patch("/api/v1/admin/agency/settings/", {"sync_interval_minutes": 5}, format="json").status_code == 403


def test_settings_guard_the_cutover(data):
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    every15, _ = IntervalSchedule.objects.get_or_create(every=15, period="minutes")
    PeriodicTask.objects.create(name="agency: sync panel admins (PAMP)", task="apps.agency.tasks.sync_panel_admins",
                                interval=every15)
    c = client(is_superadmin=True)
    assert c.patch("/api/v1/admin/agency/settings/", {"enforcement_enabled": True}, format="json").status_code == 400
    assert c.patch("/api/v1/admin/agency/settings/", {"sync_enabled": True}, format="json").status_code == 400
    assert get_setting("agency_sync_enabled") in (False, None)
    r = c.patch("/api/v1/admin/agency/settings/", {"sync_interval_minutes": 10}, format="json")
    assert r.status_code == 200 and PeriodicTask.objects.get(name="agency: sync panel admins (PAMP)").interval.every == 10
    r = c.patch("/api/v1/admin/agency/settings/", {"sync_enabled": True, "confirm": "FINLAND-STOPPED"}, format="json")
    assert r.status_code == 200 and r.json()["writes_enabled"] is True
