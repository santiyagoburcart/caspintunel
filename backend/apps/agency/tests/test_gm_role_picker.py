"""v1.27.1: the manager's "admin role" picker = PasarGuard admin roles by name only —
the group's allowed roles, or every non-owner role when staff restricted none; owner
roles never; no manager API response mentions inbounds."""
import json

import pytest

from apps.agency import managers
from apps.agency.models import GroupManagerAssignment
from apps.common.models import AuditLog

from .test_gm_admin_tools import GOOD, _users_api
from .test_group_managers import M, make_manager, manager_client, pg, staff_client  # noqa: F401

pytestmark = pytest.mark.django_db


def _no_inbounds(resp):
    assert "inbound" not in json.dumps(resp.json()).lower(), resp.json()


def test_picker_shows_only_allowed_role_names(pg):
    make_manager(staff_client(superadmin=True), pg, roles=(6, 7))
    mc = manager_client()
    r = mc.get(M + "me/")
    _no_inbounds(r)
    g = r.json()["groups"][0]
    assert g["roles"] == [{"id": 6, "name": "operator pouya"}, {"id": 7, "name": "operator ali"}]
    assert all(set(a["role"]) == {"id", "name"} for a in g["admins"] if a["role"])


def test_unrestricted_group_offers_every_non_owner_role(pg):
    make_manager(staff_client(superadmin=True), pg, roles=(6,))
    GroupManagerAssignment.objects.update(allowed_role_ids=[])            # staff restricted nothing
    mc = manager_client()
    roles = mc.get(M + "me/").json()["groups"][0]["roles"]
    assert roles == [{"id": 4, "name": "operator wir"}, {"id": 6, "name": "operator pouya"}, {"id": 7, "name": "operator ali"}]
    assert 1 not in [x["id"] for x in roles]                              # owner role never
    r = mc.post(M + "admins/", {"group_id": pg["g1"].id, "username": "anyrole", "password": GOOD, "role_id": 4,
                                "initial_gb": 5}, format="json")
    assert r.status_code == 201, r.json()
    assert mc.post(M + "admins/g1-a/role/", {"role_id": 1}, format="json").status_code == 403    # owner still refused


def test_restricted_group_refuses_other_roles_and_answers_names_only(pg):
    make_manager(staff_client(superadmin=True), pg, roles=(6,))
    mc = manager_client()
    assert mc.post(M + "admins/g1-a/role/", {"role_id": 7}, format="json").status_code == 403
    r = mc.post(M + "admins/g1-a/role/", {"role_id": 6}, format="json")
    assert r.status_code == 200 and r.json()["role"] == {"id": 6, "name": "operator pouya"}
    _no_inbounds(r)
    assert mc.post(M + "admins/g1-a/inbounds/", {"role_id": 6}, format="json").status_code == 403    # old path gone
    log = AuditLog.objects.get(action="agency.manager.role_changed")
    assert log.detail["new_role"] == "operator pouya" and "inbounds" not in log.detail


def test_no_manager_response_mentions_inbounds(pg):
    _users_api(pg, [])
    make_manager(staff_client(superadmin=True), pg)
    mc = manager_client()
    # an activity row written before v1.27.1 still carries inbounds — the manager API hides them
    a = managers.assignments(managers.GroupManager.objects.get())[0]
    managers._audit(managers.GroupManager.objects.get(), "inbounds_changed", a, admin="g1-a", inbounds=["Mix"])
    for url in ("me/", "activity/", "admins/g1-a/profile/", "admins/g1-a/users/", "accounting/",
                f"groups/{pg['g1'].id}/statement/"):
        r = mc.get(M + url)
        assert r.status_code == 200, (url, r.status_code)
        _no_inbounds(r)
    acts = [x["action"] for x in mc.get(M + "activity/").json()["results"]]
    assert "agency.manager.role_changed" in acts


def test_staff_card_shows_role_names_permissions_and_all_roles_flag(pg):
    """v1.28 Agency → Group managers card: role names, the panel role's group-manager
    permissions (from the Roles page) and "all roles" when staff restricted none."""
    from apps.accounts.models import GM_PERMS, Permission

    boss = staff_client(superadmin=True)
    made = make_manager(boss, pg, roles=(6,))
    row = boss.get("/api/v1/admin/agency/managers/").json()["results"][0]
    assert row["id"] == made["id"] and row["created_at"]
    a = row["assignments"][0]
    assert a["all_roles"] is False and [r["name"] for r in a["roles"]] == ["operator pouya"]
    assert row["panel_role"]["name"]
    perms = {p["code"]: p["on"] for p in row["permissions"]}
    assert set(perms) == set(GM_PERMS) and all(perms.values())          # the GM role gets all by default
    # take one ability off the role → the card says so
    from apps.agency.models import GroupManager

    role = GroupManager.objects.get(pk=made["id"]).staff.role
    role.permissions.remove(Permission.objects.get(code="agency.gm.accounting"))
    row = boss.get("/api/v1/admin/agency/managers/").json()["results"][0]
    assert {p["code"]: p["on"] for p in row["permissions"]}["agency.gm.accounting"] is False
    GroupManagerAssignment.objects.update(allowed_role_ids=[])
    row = boss.get("/api/v1/admin/agency/managers/").json()["results"][0]
    assert row["assignments"][0]["all_roles"] is True
