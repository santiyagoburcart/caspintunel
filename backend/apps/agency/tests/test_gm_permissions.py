"""v1.27: every group-manager ability is its own permission (agency.gm.*): with it the
API works, without it 403 (and the menu payload drops it). The Group manager role has
all of them; the seed never undoes an operator's narrowing; Super Admin never gets them."""
import pytest
from django.core.management import call_command

from apps.accounts.models import GM_PERMS, Permission, Role, Staff
from apps.agency.models import GroupManager

from .test_gm_admin_tools import GOOD, _users_api
from .test_group_managers import M, make_manager, manager_client, pg, staff_client  # noqa: F401

pytestmark = pytest.mark.django_db


def _calls(pg):
    gid = pg["g1"].id
    return {
        "agency.gm.create_admin": [("post", "admins/", {"group_id": gid, "username": "permtest", "password": GOOD,
                                                         "role_id": 6, "initial_gb": 5}),
                                    ("get", "admins/g1-a/profile/", None),
                                    ("post", "admins/g1-a/profile/", {"profile_title": "T"})],
        "agency.gm.add_volume": [("post", "admins/g1-a/add-volume/", {"gb": 5})],
        "agency.gm.toggle_admin": [("post", "admins/g1-a/disable/", {})],
        "agency.gm.admin_password": [("post", "admins/g1-a/password/", {"password": GOOD})],
        "agency.gm.admin_role": [("post", "admins/g1-a/inbounds/", {"role_id": 7})],
        "agency.gm.view_users": [("get", "admins/g1-a/users/", None)],
        "agency.gm.accounting": [("get", "accounting/", None), ("get", "admins/g1-a/statement/", None),
                                 ("get", f"groups/{gid}/statement/", None)],
        "agency.gm.activity": [("get", "activity/", None)],
    }


def _narrow(missing: str):
    s = Staff.objects.get(username="mona")
    role = Role.objects.create(name=f"GM without {missing}")
    role.permissions.set(Permission.objects.filter(code__in=["agency.group_manager", *[c for c in GM_PERMS if c != missing]]))
    s.role = role
    s.save(update_fields=["role"])


@pytest.mark.parametrize("perm", sorted(set(GM_PERMS) - {"agency.gm.view_admins"}))
def test_each_ability_needs_its_permission(pg, perm):
    _users_api(pg, [])
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    calls = _calls(pg)[perm]
    _narrow(perm)
    mc = manager_client()
    assert perm not in mc.get("/api/v1/admin/auth/me/").json()["permissions"]
    for verb, url, body in calls:
        r = getattr(mc, verb)(M + url, body, format="json") if body is not None else getattr(mc, verb)(M + url)
        assert r.status_code == 403, (perm, url, r.status_code)
        if r.json().get("permission"):
            assert r.json()["permission"] == perm
    # give it back → allowed (whatever the business result, never the permission 403)
    s = Staff.objects.get(username="mona")
    s.role.permissions.add(Permission.objects.get(code=perm))
    mc = manager_client()
    for verb, url, body in calls:
        r = getattr(mc, verb)(M + url, body, format="json") if body is not None else getattr(mc, verb)(M + url)
        assert not (r.status_code == 403 and r.json().get("permission") == perm), (perm, url, r.json())
        assert r.status_code < 400, (perm, url, r.status_code, r.json())


def test_view_admins_controls_the_admin_list(pg):
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    assert manager_client().get(M + "me/").json()["groups"][0]["admins"]
    _narrow("agency.gm.view_admins")
    d = manager_client().get(M + "me/").json()
    assert d["groups"][0]["admins"] == [] and "agency.gm.view_admins" not in d["permissions"]
    assert d["groups"][0]["roles"]                       # still what create admin needs


def test_group_manager_role_has_all_and_payload_lists_them(pg):
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    me = manager_client().get("/api/v1/admin/auth/me/").json()
    assert set(me["permissions"]) == {"agency.group_manager", *GM_PERMS}
    # still restricted to the manager API: a gm.* code never opens a staff API
    s = Staff.objects.get(username="mona")
    assert not s.has_perm("agency.view") and not s.has_perm("payment.view")


def test_seed_keeps_narrowed_roles_and_names_them_in_persian(pg):
    call_command("seed")
    gm = Role.objects.get(name="Group manager")
    assert set(GM_PERMS) <= set(gm.permissions.values_list("code", flat=True))
    gm.permissions.remove(Permission.objects.get(code="agency.gm.view_users"))
    call_command("seed")
    assert not gm.permissions.filter(code="agency.gm.view_users").exists()       # operator's choice kept
    assert gm.permissions.filter(code="agency.group_manager").exists()
    sup = Role.objects.get(name="Super Admin")
    assert not sup.permissions.filter(code__startswith="agency.gm.").exists()
    assert all(Permission.objects.get(code=c).name_fa.startswith("مدیر گروه") for c in GM_PERMS)


def test_migration_grants_existing_group_manager_roles_once():
    import importlib

    from django.apps import apps as live_apps

    role = Role.objects.create(name="Old GM")
    role.permissions.set([Permission.objects.get_or_create(code="agency.group_manager", defaults={"name": "gm"})[0]])
    other = Role.objects.create(name="Support-y")
    mig = importlib.import_module("apps.agency.migrations.0009_gm_permissions")
    mig.grant(live_apps, None)
    assert set(GM_PERMS) <= set(role.permissions.values_list("code", flat=True))
    assert not other.permissions.exists()


def test_roles_api_lists_the_section_permissions(pg):
    boss = staff_client(superadmin=True)
    call_command("seed")
    perms = boss.get("/api/v1/admin/permissions/?limit=200").json()
    rows = perms["results"] if isinstance(perms, dict) else perms
    codes = {p["code"]: p for p in rows}
    assert set(GM_PERMS) <= set(codes) and codes["agency.gm.toggle_admin"]["name_fa"] == "مدیر گروه: فعال / غیرفعال‌کردن ادمین"
    assert GroupManager.objects.count() == 0
