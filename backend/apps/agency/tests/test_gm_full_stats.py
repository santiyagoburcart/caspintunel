"""v1.36 «مدیر گروه: مشاهده آمار کامل نمایندگان»: the full PAMP numbers (same formulas as the staff Agency page)
plus live user counts / online / last activity — own groups only, server-side, and absent without the permission."""
import re

import pytest
import responses
from django.core.cache import cache

from apps.accounts.models import Role
from apps.agency import api
from apps.agency.models import PanelAdmin
from apps.agency.tests.test_group_managers import BASE, M, make_manager, manager_client, pg, staff_client  # noqa: F401

pytestmark = pytest.mark.django_db


def live_mocks(pg):  # noqa: F811
    pg["rsps"].add(responses.GET, re.compile(re.escape(BASE) + r"/api/system/users.*"),
                   json={"total_user": 40, "online_users": 7, "active_users": 30, "on_hold_users": 1, "disabled_users": 2,
                         "expired_users": 4, "limited_users": 3, "incoming_bandwidth": 0, "outgoing_bandwidth": 0})
    pg["rsps"].add(responses.GET, re.compile(re.escape(BASE) + r"/api/users\?.*sort=-online_at.*"),
                   json={"users": [{"username": "u1", "online_at": "2026-11-03T13:26:30Z"}], "total": 40})


def test_full_numbers_match_the_staff_page(pg):  # noqa: F811
    cache.clear()
    make_manager(staff_client(superadmin=True), pg)
    a = PanelAdmin.objects.get(username="g1-a")
    a.total_user_limit, a.total_user_used, a.admin_remaining, a.deleted_users_used_bytes = 90 * 1024 ** 3, 10 * 1024 ** 3, 60 * 1024 ** 3, 3 * 1024 ** 3
    a.save()
    me = manager_client().get(M + "me/").json()
    row = next(r for g in me["groups"] for r in g["admins"] if r["username"] == "g1-a")
    staff = api.admin_detail(a)
    for k in ("total_sold_fmt", "sold_limit_fmt", "hidden_fmt", "used_fmt", "remaining_fmt", "usage_percent"):
        assert row[k] == staff[k], k
    assert row["deleted_used_fmt"] == staff["deleted_used_fmt"] and row["user_counts"] == staff["user_counts"]
    live_mocks(pg)
    d = manager_client().get(M + "admins/g1-a/stats/").json()
    assert d["sold_limit_fmt"] == staff["sold_limit_fmt"]
    assert d["live"] == {"total": 40, "online": 7, "active": 30, "on_hold": 1, "disabled": 2, "expired": 4, "limited": 3,
                         "last_online": "2026-11-03T13:26:30Z", "ok": True}
    lv = manager_client().get(M + "admins/live/?u=g1-a&u=g2-owner").json()["results"]
    assert set(lv) == {"g1-a"}                                         # another group's admin is dropped
    assert manager_client().get(M + "admins/g2-owner/stats/").status_code == 403


def test_without_the_permission_nothing_extra_leaves_the_server(pg):  # noqa: F811
    cache.clear()
    make_manager(staff_client(superadmin=True), pg)
    role = Role.objects.get(name="Group manager")
    role.permissions.remove(*role.permissions.filter(code="agency.gm.full_stats"))
    me = manager_client().get(M + "me/").json()
    row = next(r for g in me["groups"] for r in g["admins"] if r["username"] == "g1-a")
    for k in ("total_sold_fmt", "sold_limit_fmt", "hidden_fmt", "user_counts", "deleted_used_fmt"):
        assert k not in row, k
    assert "hidden" not in row["bytes"] and "used_fmt" in row                   # the basic numbers stay
    assert manager_client().get(M + "admins/g1-a/stats/").status_code == 403
    assert manager_client().get(M + "admins/live/?u=g1-a").status_code == 403
