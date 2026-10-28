"""v1.27 group-manager admin tools: enable / disable (own groups, audited, shown to
staff), read-only users list (own groups, paged, filtered), support link + profile
title on create / edit, the PasarGuard admin password rule (manager + staff), and
admin-name search on the statement (frontend)."""
import json
import re

import pytest
import responses

from apps.agency import admin_crud
from apps.agency.models import PanelAdmin
from apps.common.models import AuditLog

from .test_group_managers import BASE, M, make_manager, manager_client, pg, staff_client  # noqa: F401

pytestmark = pytest.mark.django_db
GOOD = "Strong#Pass12"


# ------------------------------------------------------------------ password rule
@pytest.mark.parametrize("pw,reason", [
    ("Ab#12", "length"), ("abcdefgh#123", "upper"), ("ABCDEFGH#123", "lower"), ("Abcdefgh#xyZ1", "digits"),
    ("Abcdefgh12XY", "special"), ("Abcd efgh#12X", "charset"), ("newbie#AB12cd", "username"), (GOOD, None),
])
def test_password_rule(pw, reason):
    assert admin_crud.password_problem(pw, "newbie") == reason


def test_generated_passwords_always_pass():
    for _ in range(300):
        pw = admin_crud.generate_password()
        assert admin_crud.password_problem(pw, "someone") is None and len(pw) == 16


def test_weak_password_never_reaches_pasarguard_and_is_explained_in_persian(pg):
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    mc = manager_client()
    before = len(getattr(pg["fake"], "created", []))
    r = mc.post(M + "admins/", {"group_id": pg["g1"].id, "username": "weakling", "password": "abc12345",
                                "role_id": 6, "initial_gb": 10}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "weak_password"
    assert "۱۲ نویسه" in r.json()["detail_fa"]
    assert len(getattr(pg["fake"], "created", [])) == before
    r = mc.post(M + "admins/g1-a/password/", {"password": "short"}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "weak_password"
    assert not any(u == "g1-a" and "password" in b for u, b in pg["fake"].puts)
    # staff side: the same rule
    r = boss.patch("/api/v1/admin/agency/panel-admins/g1-a/", {"password": "weakweak1"}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "weak_password" and r.json()["detail_fa"]


# ------------------------------------------------------------------ enable / disable
def test_enable_disable_own_admin_audited_and_scoped(pg):
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    mc = manager_client()
    r = mc.post(M + "admins/g1-a/disable/", {}, format="json")
    assert r.status_code == 200 and r.json()["status"] == "disabled"
    assert ("g1-a", {"status": "disabled"}) in pg["fake"].puts
    assert PanelAdmin.objects.get(username="g1-a").status == "disabled"
    assert mc.post(M + "admins/g1-a/enable/", {}, format="json").json()["status"] == "active"
    acts = list(AuditLog.objects.filter(action__in=["agency.manager.admin_disabled", "agency.manager.admin_enabled"])
                .values_list("action", flat=True))
    assert sorted(acts) == ["agency.manager.admin_disabled", "agency.manager.admin_enabled"]
    # staff see it in the group's Activity
    act = boss.get(f"/api/v1/admin/agency/groups/{pg['g1'].id}/activity/").json()
    rows = act["results"] if isinstance(act, dict) else act
    assert {"agency.manager.admin_disabled", "agency.manager.admin_enabled"} <= {x["action"] for x in rows}
    # never another group's admin, never an owner admin, never a staff-blocked admin
    assert mc.post(M + "admins/g2-owner/disable/", {}, format="json").status_code == 403
    assert mc.post(M + "admins/other/disable/", {}, format="json").status_code == 403
    assert mc.post(M + "admins/g1-sudo/disable/", {}, format="json").status_code == 403
    PanelAdmin.objects.filter(username="g1-a").update(pamp_blocked=True)
    assert mc.post(M + "admins/g1-a/enable/", {}, format="json").status_code == 403
    # staff (not a manager) cannot use the manager API
    assert boss.post(M + "admins/g1-a/disable/", {}, format="json").status_code == 403


# ------------------------------------------------------------------ users (read-only)
def _users_api(pg, rows):
    seen = []

    def cb(req):
        from urllib.parse import parse_qs, urlparse

        q = parse_qs(urlparse(req.url).query)
        seen.append(q)
        out = [u for u in rows if u["admin"]["username"] in q.get("admin", [])]
        if q.get("status"):
            out = [u for u in out if u["status"] == q["status"][0]]
        if q.get("search"):
            out = [u for u in out if q["search"][0] in u["username"]]
        off, lim = int(q.get("offset", ["0"])[0]), int(q.get("limit", ["20"])[0])
        return 200, {}, json.dumps({"users": out[off:off + lim], "total": len(out)})
    pg["rsps"].add_callback(responses.GET, re.compile(rf"{BASE}/api/users.*"), callback=cb)
    return seen


def test_admin_users_read_only_scoped_paged_filtered(pg):
    rows = [{"username": f"u{i:02d}", "status": "active" if i % 3 else "expired", "used_traffic": i * 10 ** 9,
             "data_limit": 50 * 10 ** 9, "expire": "2026-12-01T00:00:00Z", "online_at": None, "admin": {"username": "g1-a"}}
            for i in range(25)] + [{"username": "spy", "status": "active", "admin": {"username": "g2-owner"}}]
    seen = _users_api(pg, rows)
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    mc = manager_client()
    r = mc.get(M + "admins/g1-a/users/?limit=10")
    assert r.status_code == 200 and r.json()["total"] == 25 and len(r.json()["results"]) == 10
    assert seen[-1]["admin"] == ["g1-a"]
    assert mc.get(M + "admins/g1-a/users/?limit=10&offset=20").json()["results"][-1]["username"] == "u24"
    exp = mc.get(M + "admins/g1-a/users/?status=expired").json()
    assert exp["total"] == 9 and all(u["status"] == "expired" for u in exp["results"])
    assert [u["username"] for u in mc.get(M + "admins/g1-a/users/?search=u1").json()["results"]][:2] == ["u10", "u11"]
    assert mc.get(M + "admins/g1-a/users/?status=hacked").status_code == 400
    assert mc.get(M + "admins/g2-owner/users/").status_code == 403         # other group
    assert mc.get(M + "admins/other/users/").status_code == 403            # no group
    # it is read-only: no other verb on /users/
    assert mc.post(M + "admins/g1-a/users/", {}, format="json").status_code == 403


# ------------------------------------------------------------------ support link + profile title
def test_support_link_and_profile_title_create_and_edit(pg):
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    mc = manager_client()
    r = mc.post(M + "admins/", {"group_id": pg["g1"].id, "username": "withlink", "password": GOOD, "role_id": 6,
                                "initial_gb": 10, "support_url": "https://t.me/vox_support", "profile_title": "Vox VPN"},
                format="json")
    assert r.status_code == 201, r.json()
    sent = pg["fake"].created[-1]
    assert sent["support_url"] == "https://t.me/vox_support" and sent["profile_title"] == "Vox VPN"
    pg["fake"].admins["g1-a"].update({"support_url": "https://t.me/old", "profile_title": "Old"})
    assert mc.get(M + "admins/g1-a/profile/").json()["support_url"] == "https://t.me/old"     # read from PasarGuard
    r = mc.post(M + "admins/g1-a/profile/", {"support_url": "https://t.me/new", "profile_title": "New title"}, format="json")
    assert r.status_code == 200
    assert ("g1-a", {"support_url": "https://t.me/new", "profile_title": "New title"}) in pg["fake"].puts
    log = AuditLog.objects.filter(action="agency.manager.profile_changed").latest("id")
    assert log.detail["changes"]["profile_title"] == ["Old", "New title"]
    assert mc.post(M + "admins/g1-a/profile/", {"support_url": "ftp://bad"}, format="json").status_code == 400
    assert mc.get(M + "admins/g2-owner/profile/").status_code == 403
    assert mc.post(M + "admins/g2-owner/profile/", {"profile_title": "x"}, format="json").status_code == 403
    # a manager can never set other PasarGuard fields through this
    mc.post(M + "admins/g1-a/profile/", {"profile_title": "T", "role_id": 1, "data_limit": 0}, format="json")
    assert pg["fake"].puts[-1] == ("g1-a", {"profile_title": "T"})


def test_staff_edit_reads_and_saves_support_link_and_profile_title(pg):
    boss = staff_client(superadmin=True)
    pg["fake"].admins["g1-a"].update({"support_url": "https://t.me/s", "profile_title": "PT"})
    d = boss.get("/api/v1/admin/agency/panel-admins/g1-a/").json()
    adm = d.get("admin", d)
    assert adm["support_url"] == "https://t.me/s" and adm["profile_title"] == "PT"
    r = boss.patch("/api/v1/admin/agency/panel-admins/g1-a/", {"support_url": "https://t.me/x", "profile_title": "X"}, format="json")
    assert r.status_code == 200 and ("g1-a", {"support_url": "https://t.me/x", "profile_title": "X"}) in pg["fake"].puts
