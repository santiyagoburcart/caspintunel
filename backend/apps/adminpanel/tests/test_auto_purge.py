"""Deleted users auto-purge (accounts/autopurge.py): off by default; when on, the daily task
calls purge_user for users deleted more than N days ago (PasarGuard delete included, a panel
failure purges nothing); next purge date on the Deleted users page; Super Admin settings."""
from datetime import timedelta

import pytest
import responses
from django.utils import timezone

from apps.accounts.autopurge import run
from apps.accounts.models import User
from apps.adminpanel.tests.test_user_purge import _panel, trashed  # noqa: F401
from apps.adminpanel.tests.test_user_delete import world  # noqa: F401
from apps.common.models import AuditLog
from apps.ops.schedule import ensure_auto_purge_schedule

pytestmark = pytest.mark.django_db


@pytest.fixture
def alerts(monkeypatch):
    from apps.common import staff_alert

    sent = []
    monkeypatch.setattr(staff_alert, "alert_staff", lambda text, **kw: sent.append((text, kw)) or 1)
    return sent


def _turn_on(c, days=30):
    r = c.put("/api/v1/admin/settings/", {"deleted_purge_enabled": True, "deleted_purge_days": days}, format="json")
    assert r.status_code == 200, r.data
    return r


def _age(user, days):
    User.objects.filter(pk=user.pk).update(deleted_at=timezone.now() - timedelta(days=days))


def test_off_by_default_does_nothing(trashed):  # noqa: F811
    _age(trashed["user"], 400)
    with responses.RequestsMock():                       # any panel call would fail the test
        assert run() == {"enabled": False}
    trashed["user"].refresh_from_db()
    assert trashed["user"].purged_at is None


def test_on_purges_only_users_older_than_n_days(trashed, alerts):  # noqa: F811
    c, user = trashed["c"], trashed["user"]
    _turn_on(c, 30)
    _age(user, 29)
    with responses.RequestsMock():
        assert run()["purged"] == 0
    _age(user, 31)
    with responses.RequestsMock() as rsps:
        _panel(rsps)                                     # both PasarGuard accounts deleted + verified
        res = run()
        deletes = [x for x in rsps.calls if x.request.method == "DELETE"]
    assert res["purged"] == 1 and res["failed"] == 0 and len(deletes) == 2
    user.refresh_from_db()
    assert user.purged_at and user.username.startswith("کاربر حذف‌شده")
    log = AuditLog.objects.get(action="user.purged")
    assert log.staff_label == "system" and log.detail["delete_on_panel"] is True
    run_log = AuditLog.objects.get(action="users.auto_purged")
    assert run_log.detail["purged_ids"] == [user.id] and "ali" not in str(run_log.detail)
    assert not alerts


def test_panel_failure_keeps_the_user_and_alerts(trashed, alerts):  # noqa: F811
    c, user = trashed["c"], trashed["user"]
    _turn_on(c, 30)
    _age(user, 60)
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        _panel(rsps, broken=("ali_2",))
        res = run()
        assert not [x for x in rsps.calls if x.request.method == "DELETE"]
    assert res == {"enabled": True, "days": 30, "purged": 0, "failed": 1}
    user.refresh_from_db()
    assert user.purged_at is None and user.username.startswith("deleted_")
    assert alerts and alerts[0][1]["perm"] == "users.purge"
    assert AuditLog.objects.get(action="users.auto_purged").detail["failed"][0]["code"] == "panel_error"


def test_deleted_users_page_shows_the_next_purge_date(trashed):  # noqa: F811
    c, a, user = trashed["c"], trashed["archive"], trashed["user"]
    ensure_auto_purge_schedule()
    st = c.get("/api/v1/admin/deleted-users/auto-purge/").data
    assert st["enabled"] is False and st["next_run"] is None
    assert c.get("/api/v1/admin/deleted-users/").data["results"][0]["purge_at"] is None
    _turn_on(c, 30)
    _age(user, 10)
    st = c.get("/api/v1/admin/deleted-users/auto-purge/").data
    assert st["enabled"] and st["days"] == 30 and st["next_run"] and st["due_now"] == 0
    row = c.get("/api/v1/admin/deleted-users/").data["results"][0]
    assert row["id"] == a.id and row["purge_at"]
    when = row["purge_at"] if not isinstance(row["purge_at"], str) else \
        timezone.datetime.fromisoformat(row["purge_at"].replace("Z", "+00:00"))
    expected = timezone.now() + timedelta(days=20)
    assert abs((when - expected).total_seconds()) < 86400 + 120
    assert st["next_purge_at"]


def test_only_super_admin_changes_it(trashed):  # noqa: F811
    from rest_framework.test import APIClient

    from apps.accounts.models import Permission, Role, Staff
    from apps.adminpanel.tokens import issue_tokens

    role = Role.objects.create(name="settings-only")
    role.permissions.set([Permission.objects.get_or_create(code="settings.manage", defaults={"name": "s"})[0]])
    s = Staff(username="mgr", role=role); s.set_password("Str0ngPass!"); s.save()
    c = APIClient(); c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    for body in ({"deleted_purge_enabled": True}, {"blu_stale_minutes": 10}, {"rounded_auto_enabled": False}):
        assert c.put("/api/v1/admin/settings/", body, format="json").status_code == 403
    assert c.put("/api/v1/admin/settings/", {"alert_expire_days": 4}, format="json").status_code == 200
    # the change is audited with old → new values
    _turn_on(trashed["c"], 45)
    log = AuditLog.objects.filter(action="settings.updated").order_by("-id").first()
    assert log.detail["values"]["deleted_purge_days"] == {"from": 30, "to": 45}
    assert log.detail["values"]["deleted_purge_enabled"] == {"from": False, "to": True}
