"""v1.25.2: a staff given the "Group manager" role on the Staff page is a group manager
— same record as Agency → Group managers (groups, allowed roles per group, cap), both
pages stay in sync, a manager without groups is flagged, and Persian role/permission
labels are seeded."""
import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, Staff
from apps.adminpanel.tokens import issue_tokens
from apps.agency import managers
from apps.agency.models import AdminGroup, GroupManager, GroupManagerAssignment

pytestmark = pytest.mark.django_db
CATALOG = {
    1: {"id": 1, "name": "owner", "is_owner": True, "inbounds": [], "all_inbounds": True},
    6: {"id": 6, "name": "operator pouya", "is_owner": False, "inbounds": ["Mix"], "all_inbounds": False},
    7: {"id": 7, "name": "operator ali", "is_owner": False, "inbounds": ["ali"], "all_inbounds": False},
}


@pytest.fixture(autouse=True)
def catalog(monkeypatch):
    monkeypatch.setattr(managers, "roles_catalog", lambda fresh=False: CATALOG)


@pytest.fixture
def boss():
    s = Staff(username="boss", is_superadmin=True)
    s.set_password("Str0ngPass!")
    s.save()
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    return c


@pytest.fixture
def groups():
    return (AdminGroup.objects.create(owner_username="VEX2", member_usernames="Iman,Iman2"),
            AdminGroup.objects.create(owner_username="Mostafa-ho", member_usernames="mohsen"))


def _create(boss, **extra):
    body = {"username": "imantorabian", "password": "Str0ngPass!1", "role": managers.gm_role().id, **extra}
    return boss.post("/api/v1/admin/staff/", body, format="json")


def test_gm_role_on_staff_page_creates_the_linked_manager_without_groups(boss, groups):
    r = _create(boss)
    assert r.status_code == 201, r.content
    s = Staff.objects.get(username="imantorabian")
    m = GroupManager.objects.get(staff=s)
    assert m.username == "imantorabian" and m.password == s.password_hash and m.is_active
    assert s.is_group_manager
    assert r.json()["group_manager"]["warnings"] == ["no_group"]
    row = next(x for x in boss.get("/api/v1/admin/agency/managers/").json()["results"] if x["id"] == m.id)
    assert row["staff_username"] == "imantorabian" and "no_group" in row["warnings"]
    assert boss.get("/api/v1/admin/staff/").json()["results"][1]["group_manager"]["warnings"] == ["no_group"] \
        or any(x["group_manager"] and x["group_manager"]["warnings"] == ["no_group"]
               for x in boss.get("/api/v1/admin/staff/").json()["results"])


def test_staff_page_and_agency_page_edit_the_same_record(boss, groups):
    vox, other = groups
    sid = _create(boss).json()["id"]
    r = boss.patch(f"/api/v1/admin/staff/{sid}/", {"group_manager": {
        "assignments": [{"group_id": vox.id, "role_ids": [6, 7]}], "max_unapproved_gb": "50"}}, format="json")
    assert r.status_code == 200, r.content
    gm = r.json()["group_manager"]
    assert gm["assignments"] == [{"group_id": vox.id, "group": "VEX2", "role_ids": [6, 7]}]
    assert str(gm["max_unapproved_gb"]).startswith("50") and gm["warnings"] == []
    m = GroupManager.objects.get(staff_id=sid)
    row = next(x for x in boss.get("/api/v1/admin/agency/managers/").json()["results"] if x["id"] == m.id)
    assert [a["group_id"] for a in row["assignments"]] == [vox.id]

    # Agency → Group managers changes it back; the Staff page shows the same
    r = boss.patch(f"/api/v1/admin/agency/managers/{m.id}/", {"assignments": [{"group_id": other.id, "role_ids": [6]}],
                                                             "max_unapproved_gb": None}, format="json")
    assert r.status_code == 200, r.content
    gm = boss.get(f"/api/v1/admin/staff/{sid}/").json()["group_manager"]
    assert [(a["group_id"], a["role_ids"]) for a in gm["assignments"]] == [(other.id, [6])]
    assert gm["max_unapproved_gb"] is None


def test_owner_roles_and_unknown_groups_are_refused(boss, groups):
    sid = _create(boss).json()["id"]
    r = boss.patch(f"/api/v1/admin/staff/{sid}/", {"group_manager": {
        "assignments": [{"group_id": groups[0].id, "role_ids": [1]}]}}, format="json")
    assert r.status_code == 400 and "owner" in str(r.json()["group_manager"])
    r = boss.patch(f"/api/v1/admin/staff/{sid}/", {"group_manager": {"assignments": [{"group_id": 999, "role_ids": [6]}]}},
                   format="json")
    assert r.status_code == 400
    assert not GroupManagerAssignment.objects.exists()


def test_groups_need_the_role_and_removing_it_unlinks(boss, groups):
    other = Role.objects.create(name="Support-x")
    r = boss.post("/api/v1/admin/staff/", {"username": "sup", "password": "Str0ngPass!1", "role": other.id,
                                           "group_manager": {"assignments": [{"group_id": groups[0].id, "role_ids": [6]}]}},
                  format="json")
    assert r.status_code == 400 and not Staff.objects.filter(username="sup").exists()     # atomic

    sid = _create(boss, group_manager={"assignments": [{"group_id": groups[0].id, "role_ids": [6]}]}).json()["id"]
    m = GroupManager.objects.get(staff_id=sid)
    r = boss.patch(f"/api/v1/admin/staff/{sid}/", {"role": other.id}, format="json")
    assert r.status_code == 200 and r.json()["group_manager"] is None
    m.refresh_from_db()
    assert m.staff_id is None and not m.is_active
    assert not Staff.objects.get(pk=sid).is_group_manager
    # giving the role back re-links the same manager with its groups
    r = boss.patch(f"/api/v1/admin/staff/{sid}/", {"role": managers.gm_role().id}, format="json")
    m.refresh_from_db()
    assert m.staff_id == sid and m.is_active and r.json()["group_manager"]["id"] == m.id
    assert r.json()["group_manager"]["warnings"] == []


def test_password_from_staff_page_is_the_managers_password(boss, groups):
    sid = _create(boss).json()["id"]
    boss.patch(f"/api/v1/admin/staff/{sid}/", {"password": "An0therPass!"}, format="json")
    s, m = Staff.objects.get(pk=sid), GroupManager.objects.get(staff_id=sid)
    assert s.check_password("An0therPass!") and m.password == s.password_hash


def test_agency_page_links_an_existing_gm_staff_instead_of_refusing(boss, groups):
    s = Staff(username="lateman", role=managers.gm_role())
    s.set_password("Str0ngPass!")
    s.save()
    r = boss.post("/api/v1/admin/agency/managers/", {"username": "lateman", "assignments": [
        {"group_id": groups[0].id, "role_ids": [6]}]}, format="json")
    assert r.status_code in (200, 201), r.content
    m = GroupManager.objects.get(username="lateman")
    assert m.staff_id == s.pk
    s.refresh_from_db()
    assert s.check_password("Str0ngPass!")                     # keeps its own password
    plain = Staff(username="plainstaff", role=Role.objects.create(name="r-plain"))
    plain.set_password("Str0ngPass!")
    plain.save()
    r = boss.post("/api/v1/admin/agency/managers/", {"username": "plainstaff", "password": "Str0ngPass!2",
                                                     "assignments": [{"group_id": groups[0].id, "role_ids": [6]}]},
                  format="json")
    assert r.status_code == 409


def test_migration_links_existing_gm_role_staff(groups):
    import importlib

    from django.apps import apps as live_apps

    s = Staff(username="imantorabian", role=managers.gm_role())
    s.set_password("Str0ngPass!")
    s.save()
    assert s.group_manager_row is None
    mig = importlib.import_module("apps.agency.migrations.0008_link_group_manager_staff")
    mig.link(live_apps, None)
    m = GroupManager.objects.get(staff=s)
    assert m.username == "imantorabian" and not m.assignments.exists()
    mig.link(live_apps, None)                                    # idempotent
    assert GroupManager.objects.filter(username="imantorabian").count() == 1


def test_staff_options_endpoint(boss, groups):
    d = boss.get("/api/v1/admin/staff/group-manager-options/").json()
    assert {g["name"] for g in d["groups"]} == {"VEX2", "Mostafa-ho"}
    assert [r["id"] for r in d["roles"]] == [6, 7]                 # owner role never offered


def test_seed_gives_persian_labels(boss):
    call_command("seed")
    assert not Permission.objects.filter(name_fa="").exists()
    gm = Role.objects.get(name="Group manager")
    assert gm.name_fa == "مدیر گروه" and gm.description_fa
    assert Role.objects.get(name="Super Admin").name_fa == "مدیر ارشد"
    perms = boss.get("/api/v1/admin/permissions/?limit=200").json()
    rows = perms["results"] if isinstance(perms, dict) else perms
    assert all(p["name_fa"] for p in rows)
    # an operator's own Persian edit survives the next seed
    Role.objects.filter(pk=gm.pk).update(name_fa="سرگروه")
    call_command("seed")
    assert Role.objects.get(pk=gm.pk).name_fa == "سرگروه"


def test_group_names_show_everywhere(boss, groups):
    from apps.agency.models import PanelAdmin

    from apps.settings_app.utils import set_setting

    set_setting("agency_sync_enabled", True, "bool")          # group writes open after the cut-over
    vox, _ = groups
    for u in ("VEX2", "Iman", "Iman2"):
        PanelAdmin.objects.get_or_create(username=u)
    sid = _create(boss, group_manager={"assignments": [{"group_id": vox.id, "role_ids": [6]}]}).json()["id"]
    r = boss.put(f"/api/v1/admin/agency/groups/{vox.id}/", {"name": "Vox", "owner": "VEX2",
                                                         "members": ["Iman", "Iman2"], "note": ""}, format="json")
    assert r.status_code == 200, r.content
    d = boss.get("/api/v1/admin/agency/admins/").json()
    assert {"id": vox.id, "owner": "VEX2", "name": "Vox"} in d["groups"]
    iman = next(x for x in d["results"] if x["username"] == "Iman")
    assert [g["name"] for g in iman["groups"]] == ["Vox"]
    assert boss.get(f"/api/v1/admin/staff/{sid}/").json()["group_manager"]["assignments"][0]["group"] == "Vox"
    m = GroupManager.objects.get(staff_id=sid)
    row = next(x for x in boss.get("/api/v1/admin/agency/managers/").json()["results"] if x["id"] == m.id)
    assert row["assignments"][0]["group"] == "Vox"
