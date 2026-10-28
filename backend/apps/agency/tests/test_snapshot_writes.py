"""v1.25.2: the sync only writes snapshot rows whose usage changed (binlog growth fix)
and keeps PAMP's results: deleted users still move their usage into sold volume."""
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.agency.models import PanelAdmin, UserTrafficSnapshot
from apps.agency.tasks import track_deleted_users

pytestmark = pytest.mark.django_db


def _users(**used):
    return [{"username": u, "used_traffic": b} for u, b in used.items()]


def _writes(ctx):
    return [q["sql"] for q in ctx.captured_queries
            if q["sql"].lstrip().upper().startswith(("UPDATE", "INSERT", "DELETE"))
            and "agency_user_traffic_snapshot" in q["sql"]]


def test_unchanged_usage_writes_nothing_and_changes_write_only_their_rows():
    pa = PanelAdmin.objects.create(username="r1")
    track_deleted_users(pa, _users(a=10, b=20, c=30))
    assert UserTrafficSnapshot.objects.filter(panel_admin=pa).count() == 3
    seen = dict(UserTrafficSnapshot.objects.values_list("user_username", "last_seen"))

    with CaptureQueriesContext(connection) as ctx:
        track_deleted_users(pa, _users(a=10, b=20, c=30))
    assert _writes(ctx) == []
    assert dict(UserTrafficSnapshot.objects.values_list("user_username", "last_seen")) == seen

    with CaptureQueriesContext(connection) as ctx:
        track_deleted_users(pa, _users(a=10, b=25, c=30))
    assert len(_writes(ctx)) == 1
    rows = {s.user_username: s for s in UserTrafficSnapshot.objects.filter(panel_admin=pa)}
    assert rows["b"].used_traffic_bytes == 25 and rows["b"].last_seen > seen["b"]
    assert rows["a"].last_seen == seen["a"]


def test_deleted_and_new_users_keep_pamp_results():
    pa = PanelAdmin.objects.create(username="r2")
    track_deleted_users(pa, _users(a=100, b=200))
    track_deleted_users(pa, _users(a=150, d=5))           # b deleted, d new, a changed
    pa.refresh_from_db()
    assert pa.deleted_users_used_bytes == 200
    assert dict(UserTrafficSnapshot.objects.filter(panel_admin=pa)
                .values_list("user_username", "used_traffic_bytes")) == {"a": 150, "d": 5}
