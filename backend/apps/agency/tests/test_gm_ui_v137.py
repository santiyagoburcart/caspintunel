"""v1.37 group-manager UI backend: «ادمین‌های گروه» paged / searched over all / sorted, activity typed + filtered +
paged (incl. own payments / requests), notices paged + mark one read, own sound prefs and push endpoints."""
from decimal import Decimal

import pytest

from apps.agency import billing, ledger
from apps.agency.models import AdminGroup, AgencyNotice, GroupManager, LedgerEntry, PanelAdmin
from apps.agency.tests.test_group_managers import GB, M, make_manager, manager_client, pg, staff_client  # noqa: F401
from apps.common.models import write_audit

pytestmark = pytest.mark.django_db


def many_admins(pg, n=25):  # noqa: F811
    g = pg["g1"]
    names = [f"g1-x{i:02d}" for i in range(n)]
    for i, u in enumerate(names):
        PanelAdmin.objects.create(username=u, has_data_limit=True, admin_limit_bytes=100 * GB, last_limit_bytes=100 * GB,
                                  total_user_used=i * GB)
    g.member_usernames = ",".join(g.get_members() + names)
    g.save()
    return names


def test_admins_list_pages_searches_all_and_sorts(pg):  # noqa: F811
    make_manager(staff_client(superadmin=True), pg)
    names = many_admins(pg)
    mc = manager_client()
    d = mc.get(M + "admins/").json()
    assert d["page_size"] == 20 and len(d["results"]) == 20 and d["pages"] == 2 and d["count"] >= 27
    assert d["results"][0]["username"] == "g1-owner"                       # the owner first by name sort
    assert "g2-owner" not in [r["username"] for r in mc.get(M + "admins/?page=2").json()["results"]]
    # search runs over ALL admins (x24 lives on page 2 of the plain list)
    r = mc.get(M + "admins/?q=x24").json()
    assert [x["username"] for x in r["results"]] == ["g1-x24"] and r["count"] == 1
    top = mc.get(M + "admins/?sort=usage").json()["results"][0]
    assert top["username"] == names[-1]                                      # highest usage first
    LedgerEntry.objects.create(admin_username="g1-x03", kind="manual_charge", amount=Decimal("5000"), date=ledger.today())
    assert mc.get(M + "admins/?sort=debt").json()["results"][0]["username"] == "g1-x03"
    assert mc.get(M + "me/?lite=1").json()["groups"][0]["admins"] == []
    assert mc.get(M + "admins/?page_size=50").json()["page_size"] == 50


def test_activity_types_filters_and_pages(pg):  # noqa: F811
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    m = GroupManager.objects.get(username="mona")
    gid = pg["g1"].id
    for i in range(35):
        write_audit(action="agency.manager.volume_added", staff="manager:mona", detail={"group_id": gid, "admin": "g1-a", "gb": 5})
    write_audit(action="agency.manager.admin_disabled", staff="manager:mona", detail={"group_id": gid, "admin": "g1-unl"})
    write_audit(action="agency.manager.volume_added", staff="manager:x", detail={"group_id": pg["g2"].id, "admin": "g2-owner"})
    billing.create_request("g1-a", 5, manager=m)                              # own request → in the feed
    mc = manager_client()
    d = mc.get(M + "activity/").json()
    assert d["count"] == 37 and len(d["results"]) == 30 and d["pages"] == 2
    assert {r["type"] for r in d["results"]} >= {"volume", "status", "request"}
    assert mc.get(M + "activity/?type=status").json()["count"] == 1
    assert mc.get(M + "activity/?type=request").json()["results"][0]["admin"] == "g1-a"
    assert mc.get(M + "activity/?admin=g1-unl").json()["count"] == 1
    assert mc.get(M + "activity/?admin=g2-owner").json()["count"] == 0       # another group's admin: nothing
    assert "g1-a" in mc.get(M + "activity/").json()["admins"]


def test_notices_pages_and_mark_one_read(pg):  # noqa: F811
    make_manager(staff_client(superadmin=True), pg)
    m = GroupManager.objects.get(username="mona")
    for i in range(25):
        AgencyNotice.objects.create(manager=m, kind="x", title=f"n{i}")
    mc = manager_client()
    d = mc.get(M + "notices/?page=2").json()
    assert d["count"] == 25 and d["pages"] == 2 and len(d["results"]) == 5 and d["unread"] == 25
    one = d["results"][0]["id"]
    assert mc.post(M + "notices/", {"id": one}, format="json").json()["unread"] == 24
    assert mc.post(M + "notices/", {"read": True}, format="json").json()["unread"] == 0


def test_manager_sound_prefs_and_push(pg, settings):  # noqa: F811
    make_manager(staff_client(superadmin=True), pg)
    mc = manager_client()
    assert mc.get(M + "prefs/").json() == {"sound": True, "volume": 60}
    assert mc.patch(M + "prefs/", {"sound": False, "volume": 30}, format="json").json() == {"sound": False, "volume": 30}
    assert mc.get(M + "push/").json()["subscriptions"] == 0
    settings.VAPID_PUBLIC_KEY = settings.VAPID_PRIVATE_KEY = ""
    assert mc.post(M + "push/subscribe/", {"subscription": {}}, format="json").status_code == 503
