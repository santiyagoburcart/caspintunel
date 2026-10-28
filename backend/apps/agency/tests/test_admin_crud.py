"""Create / edit / delete PasarGuard admins from the Agency panel (admin_crud):
payloads match the panel's AdminCreate / AdminModify schema, panel first then
read back, optional price + quota charge + group, typed-username delete,
permissions, cut-over gate, audit without passwords. Panel HTTP is mocked."""
import json

import pytest
import responses
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, Staff
from apps.adminpanel.tokens import issue_tokens
from apps.agency.models import AdminGroup, AdminPrice, LedgerEntry, PanelAdmin
from apps.common.models import AuditLog
from apps.panel.models import Panel
from apps.settings_app.models import ValueType
from apps.settings_app.utils import set_setting

pytestmark = pytest.mark.django_db
BASE = "https://sigma.test"
GB = 1024 ** 3


def client(perms=None, superadmin=False, name="boss"):
    role = None
    if perms:
        role = Role.objects.create(name=f"r-{name}")
        role.permissions.set([Permission.objects.get_or_create(code=c, defaults={"name": c})[0] for c in perms])
    s = Staff(username=name, role=role, is_superadmin=superadmin)
    s.set_password("x-Str0ng!")
    s.save()
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    return c


@pytest.fixture
def panel():
    set_setting("agency_sync_enabled", True, ValueType.BOOL)           # cut-over done → writes open
    return Panel.objects.create(name="sigma", base_url=BASE, admin_username="u", admin_password_enc="p", is_active=True)


def admin_json(username="newbie", **kw):
    return {"id": 9, "username": username, "telegram_id": kw.get("telegram_id"), "discord_webhook": None,
            "sub_domain": None, "profile_title": None, "support_url": None, "custom_variables": [], "note": kw.get("note"),
            "notification_enable": None, "total_users": 0, "used_traffic": 0, "data_limit": kw.get("data_limit", 0),
            "status": "active", "sub_template": None, "role": {"id": 2, "name": "reseller", "is_owner": False},
            "is_disabled": False, "is_limited": False}


def mock_panel(rsps, username="newbie", **kw):
    rsps.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"})
    rsps.add(responses.GET, f"{BASE}/api/admins", json={"admins": [admin_json(username, **kw)], "total": 1})


@responses.activate
def test_options_read_roles_and_their_access_live(panel):
    responses.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"})
    responses.add(responses.GET, f"{BASE}/api/admin-roles/simple", json={"roles": [
        {"id": 1, "name": "owner", "is_owner": True}, {"id": 2, "name": "reseller", "is_owner": False}], "total": 2})
    responses.add(responses.GET, f"{BASE}/api/groups/simple", json={"groups": [{"id": 5, "name": "Germany"}, {"id": 6, "name": "Finland"}]})
    responses.add(responses.GET, f"{BASE}/api/user_templates/simple", json={"templates": [{"id": 3, "name": "30d-50GB"}]})
    responses.add(responses.GET, f"{BASE}/api/admin-role/1", json={"access": {"allowed_group_ids": None}, "limits": {}})
    responses.add(responses.GET, f"{BASE}/api/admin-role/2", json={"access": {"allowed_group_ids": [5], "allowed_template_ids": [3]},
                                                                  "limits": {"max_users": 100, "data_limit_max": None}})
    d = client(["agency.manage"]).get("/api/v1/admin/agency/panel-admins/options/").json()
    assert d["panels"] == [{"id": panel.id, "name": "sigma", "agency": True}]
    roles = {r["name"]: r for r in d["roles"]}
    assert roles["owner"]["is_owner"] and roles["owner"]["all_groups"]
    assert roles["reseller"]["groups"] == ["Germany"] and roles["reseller"]["templates"] == ["30d-50GB"]
    assert roles["reseller"]["limits"] == {"max_users": 100}
    assert "create" in d["notify_keys"] and "max_users" in d["limit_keys"]


@responses.activate
def test_create_sends_schema_payload_then_price_charge_group_and_card(panel):
    PanelAdmin.objects.create(username="owner1")
    g = AdminGroup.objects.create(owner_username="owner1", member_usernames="", name="North")
    mock_panel(responses, data_limit=600 * GB)
    responses.add(responses.POST, f"{BASE}/api/admin", json=admin_json(), status=200)
    c = client(["agency.manage", "agency.accounting"])
    r = c.post("/api/v1/admin/agency/panel-admins/", {
        "username": "newbie", "password": "Secr3t-Pass99", "role_id": 2, "telegram_id": "123456",
        "discord_webhook": "https://discord.com/api/webhooks/x", "note": "north reseller", "status": "active",
        "custom_variables": [{"key": "city", "value": "Rasht"}, {"key": "", "value": "skip"}],
        "notification_enable": {"create": True, "delete": False},
        "permission_overrides": {"max_users": 50},
        "limit_value": 600, "limit_unit": "GB", "price_per_gb": 100, "group_id": g.id,
    }, format="json")
    assert r.status_code == 201, r.json()
    sent = json.loads([call.request.body for call in responses.calls if call.request.method == "POST"
                       and call.request.url.endswith("/api/admin")][0])
    assert sent["username"] == "newbie" and sent["password"] == "Secr3t-Pass99" and sent["role_id"] == 2
    assert sent["telegram_id"] == 123456 and sent["data_limit"] == 600 * GB and sent["note"] == "north reseller"
    assert sent["custom_variables"] == [{"key": "city", "value": "Rasht"}]
    assert sent["notification_enable"]["delete"] is False and sent["notification_enable"]["modify"] is True
    assert sent["permission_overrides"]["max_users"] == 50 and sent["permission_overrides"]["expire_max"] is None
    d = r.json()
    assert d["password"] == "Secr3t-Pass99" and d["tracked"] is True and d["group"] == "North"
    assert PanelAdmin.objects.get(username="newbie").admin_limit_bytes == 600 * GB
    assert AdminPrice.objects.get(admin_username="newbie").price_per_gb == 100
    entry = LedgerEntry.objects.get(admin_username="newbie")
    assert entry.kind == "quota_charge" and entry.amount == 60000 and entry.new_limit_bytes == 600 * GB
    g.refresh_from_db()
    assert "newbie" in g.member_usernames
    audit = AuditLog.objects.get(action="agency.admin_created")
    assert "Secr3t" not in json.dumps(audit.detail) and audit.detail["username"] == "newbie"


@pytest.mark.parametrize("bad, field", [
    ({"username": "a b", "password": "Secr3t-Pass99", "role_id": 2}, "username"),
    ({"username": "newbie", "password": "short", "role_id": 2}, "password"),
    ({"username": "newbie", "password": "Secr3t-Pass99"}, "role_id"),
    ({"username": "newbie", "password": "Secr3t-Pass99", "role_id": 2, "telegram_id": "abc"}, "telegram_id"),
    ({"username": "newbie", "password": "Secr3t-Pass99", "role_id": 2, "discord_webhook": "ftp://x"}, "discord_webhook"),
])
def test_create_validation_before_any_panel_call(panel, bad, field):
    with responses.RequestsMock() as rsps:            # any HTTP call would fail the test
        r = client(["agency.manage"]).post("/api/v1/admin/agency/panel-admins/", bad, format="json")
        assert len(rsps.calls) == 0
    assert r.status_code == 400 and r.json()["field"] == field


@responses.activate
def test_create_conflict_and_permissions_and_gate(panel):
    responses.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"})
    responses.add(responses.POST, f"{BASE}/api/admin", json={"detail": "Admin already exists"}, status=409)
    body = {"username": "taken", "password": "Secr3t-Pass99", "role_id": 2}
    r = client(["agency.manage"]).post("/api/v1/admin/agency/panel-admins/", body, format="json")
    assert r.status_code == 409 and r.json()["code"] == "exists"
    assert not PanelAdmin.objects.filter(username="taken").exists()
    assert client(["agency.view"], name="v").post("/api/v1/admin/agency/panel-admins/", body, format="json").status_code == 403
    r = client(["agency.manage"], name="m").post("/api/v1/admin/agency/panel-admins/", {**body, "price_per_gb": 5}, format="json")
    assert r.status_code == 403
    set_setting("agency_sync_enabled", False, ValueType.BOOL)
    r = client(["agency.manage"], name="g").post("/api/v1/admin/agency/panel-admins/", body, format="json")
    assert r.status_code == 409 and r.json()["code"] == "pre_cutover"


@responses.activate
def test_create_on_another_panel_is_not_tracked(panel):
    other = Panel.objects.create(name="other", base_url="https://other.test", admin_username="u", admin_password_enc="p", is_active=True)
    responses.add(responses.POST, "https://other.test/api/admin/token", json={"access_token": "t"})
    responses.add(responses.POST, "https://other.test/api/admin", json=admin_json("xone"))
    responses.add(responses.GET, "https://other.test/api/admins", json={"admins": [admin_json("xone")]})
    r = client(["agency.manage"]).post("/api/v1/admin/agency/panel-admins/", {
        "panel": other.id, "username": "xone", "password": "Secr3t-Pass99", "role_id": 2, "limit_value": 1, "limit_unit": "TB"},
        format="json")
    assert r.status_code == 201, r.json()
    assert r.json()["tracked"] is False and r.json()["limit_bytes"] == 1024 * GB
    assert not PanelAdmin.objects.filter(username="xone").exists() and not LedgerEntry.objects.exists()


@responses.activate
def test_modify_sends_only_changed_fields_and_never_logs_password(panel):
    PanelAdmin.objects.create(username="ali")
    mock_panel(responses, "ali", note="new note")
    responses.add(responses.PUT, f"{BASE}/api/admin/ali", json=admin_json("ali"))
    c = client(["agency.manage"])
    assert c.get("/api/v1/admin/agency/panel-admins/ali/").json()["role_name"] == "reseller"
    r = c.patch("/api/v1/admin/agency/panel-admins/ali/", {"note": "new note", "password": "Another-Pass#12", "status": "disabled"},
                format="json")
    assert r.status_code == 200 and r.json()["password_changed"] is True
    put = json.loads([x.request.body for x in responses.calls if x.request.method == "PUT"][0])
    assert put == {"note": "new note", "password": "Another-Pass#12", "status": "disabled"}
    assert PanelAdmin.objects.get(username="ali").status == "disabled"
    a = AuditLog.objects.get(action="agency.admin_updated")
    assert a.detail["password_reset"] is True and "Another" not in json.dumps(a.detail)


@responses.activate
def test_delete_needs_typed_username_and_cleans_up_but_keeps_ledger(panel):
    PanelAdmin.objects.create(username="ali")
    PanelAdmin.objects.create(username="bea")
    g1 = AdminGroup.objects.create(owner_username="bea", member_usernames="ali")
    AdminGroup.objects.create(owner_username="ali", member_usernames="bea")
    LedgerEntry.objects.create(admin_username="ali", kind="payment", amount=10, date="2026-10-01")
    responses.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"})
    responses.add(responses.DELETE, f"{BASE}/api/admin/ali", status=204)
    c = client(["agency.manage"])
    r = c.delete("/api/v1/admin/agency/panel-admins/ali/", {"confirm": "Ali"}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "confirm"
    assert not [x for x in responses.calls if x.request.method == "DELETE"]
    r = c.delete("/api/v1/admin/agency/panel-admins/ali/", {"confirm": "ali"}, format="json")
    assert r.status_code == 200
    assert not PanelAdmin.objects.filter(username="ali").exists()
    g1.refresh_from_db()
    assert "ali" not in g1.member_usernames and not AdminGroup.objects.filter(owner_username="ali").exists()
    assert LedgerEntry.objects.filter(admin_username="ali").count() == 1
    assert AuditLog.objects.filter(action="agency.admin_deleted").exists()
