"""Account-group management from the admin panel (PAMP account groups) and its
effect on the reseller portal's group view."""
import pytest
import responses
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, Staff
from apps.adminpanel.tokens import issue_tokens
from apps.agency.models import AdminGroup, PanelAdmin
from apps.common.models import AuditLog
from apps.panel.models import Panel
from apps.settings_app.models import ValueType
from apps.settings_app.utils import set_setting

pytestmark = pytest.mark.django_db
GB = 1024 ** 3
BASE = "https://sigma.test"
URL = "/api/v1/admin/agency/groups/"


@pytest.fixture(autouse=True)
def setup():
    cache.clear()
    Panel.objects.create(name="sigma", base_url=BASE, admin_username="u", admin_password_enc="p", is_active=True)
    for n, sold, used, uc, ac in [("ali", 100, 40, 10, 9), ("bea", 50, 20, 5, 1), ("cyrus", 30, 30, 3, 3), ("dana", 1, 1, 1, 0)]:
        PanelAdmin.objects.create(username=n, total_user_limit=sold * GB, total_user_used=used * GB,
                                  user_count=uc, active_user_count=ac)
    set_setting("agency_sync_enabled", True, ValueType.BOOL)       # writes open after the cut-over
    set_setting("agency_portal_enabled", True, ValueType.BOOL)


def staff(perms=None):
    s = Staff(username="boss", is_superadmin=perms is None)
    if perms is not None:
        role = Role.objects.create(name="r")
        role.permissions.set([Permission.objects.get_or_create(code=c, defaults={"name": c})[0] for c in perms])
        s.role = role
    s.set_password("x-Str0ng!"); s.save()
    c = APIClient(); c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    return c


def portal_me(username):
    with responses.RequestsMock() as rsps:
        rsps.add("POST", f"{BASE}/api/admin/token", json={"access_token": "x"})
        tok = APIClient().post("/api/v1/agency/portal/login/", {"username": username, "password": "pw"}, format="json").json()["token"]
    c = APIClient(); c.credentials(HTTP_AUTHORIZATION=f"Agency {tok}")
    me = c.get("/api/v1/agency/portal/me/").json()
    return me["mode"], [a["username"] for a in me["accounts"]]


def test_create_rename_change_members_and_delete_with_portal_visibility():
    c = staff()
    r = c.post(URL, {"name": "North", "owner": "ali", "members": ["bea", "ali", "bea"], "note": "n"}, format="json")
    assert r.status_code == 201, r.content
    gid = r.json()["id"]
    g = AdminGroup.objects.get()
    assert (g.name, g.owner_username, g.member_usernames) == ("North", "ali", "bea")   # owner + duplicate dropped, PAMP comma format
    assert portal_me("ali") == ("group", ["ali", "bea"]) and portal_me("bea") == ("single", ["bea"])

    row = c.get(URL).json()["results"][0]
    assert row["totals"] == {"accounts": 2, "total_sold_fmt": "150.00 GB", "used_fmt": "60.00 GB", "user_count": 15, "active_user_count": 10,
                             "total_sold_bytes": 150 * GB, "used_bytes": 60 * GB}
    assert [(m["username"], m["role"]) for m in row["rows"]] == [("ali", "owner"), ("bea", "member")]

    # rename + add/remove members
    assert c.put(f"{URL}{gid}/", {"name": "South", "owner": "ali", "members": "cyrus,dana"}, format="json").status_code == 200
    assert portal_me("ali") == ("group", ["ali", "cyrus", "dana"])
    # change the owner: the old owner loses the group view
    assert c.put(f"{URL}{gid}/", {"name": "South", "owner": "cyrus", "members": ["ali"]}, format="json").status_code == 200
    assert portal_me("cyrus") == ("group", ["cyrus", "ali"]) and portal_me("ali") == ("single", ["ali"])

    assert c.delete(f"{URL}{gid}/").status_code == 204
    assert not AdminGroup.objects.exists() and portal_me("cyrus") == ("single", ["cyrus"])
    assert set(AuditLog.objects.filter(action__startswith="agency.group_").values_list("action", flat=True)) == {
        "agency.group_created", "agency.group_updated", "agency.group_deleted"}


def test_validation():
    c = staff()
    assert c.post(URL, {"owner": "", "members": []}, format="json").json()["code"] == "owner_required"
    assert c.post(URL, {"owner": "ghost", "members": []}, format="json").json()["code"] == "unknown_owner"
    r = c.post(URL, {"owner": "ali", "members": ["bea", "nobody"]}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "unknown_member" and r.json()["usernames"] == ["nobody"]
    gid = c.post(URL, {"owner": "ali", "members": ["bea"]}, format="json").json()["id"]
    assert c.post(URL, {"owner": "ali", "members": []}, format="json").json()["code"] == "owner_taken"
    other = c.post(URL, {"owner": "cyrus", "members": []}, format="json").json()["id"]
    assert c.put(f"{URL}{other}/", {"owner": "ali", "members": []}, format="json").json()["code"] == "owner_taken"
    assert c.put(f"{URL}999/", {"owner": "dana", "members": []}, format="json").status_code == 404
    # a member that is no longer on the panel can stay in a group that already had it
    AdminGroup.objects.filter(pk=gid).update(member_usernames="bea,gone")
    assert c.put(f"{URL}{gid}/", {"owner": "ali", "members": ["bea", "gone"], "name": "x"}, format="json").status_code == 200
    assert c.get(URL).json()["results"][0]["missing"] == ["gone"]


def test_permissions_and_cutover_gate():
    viewer = staff(["agency.view"])
    assert viewer.get(URL).status_code == 200
    assert viewer.post(URL, {"owner": "ali", "members": []}, format="json").status_code == 403
    set_setting("agency_sync_enabled", False, ValueType.BOOL)
    admin = APIClient(); s = Staff(username="root", is_superadmin=True); s.set_password("x-Str0ng!"); s.save()
    admin.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    assert admin.post(URL, {"owner": "ali", "members": []}, format="json").status_code == 409
    assert not AdminGroup.objects.exists()
