import pytest

from apps.adminpanel.tests.conftest import make_staff
from apps.ops.models import (
    BackupLog,
    BackupStatus,
    HealthCheck,
    HealthTarget,
    ResourceStat,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def boss(staff_client, superadmin):
    return staff_client(superadmin)


def test_health_endpoint_shows_latest_per_target(boss):
    HealthCheck.objects.create(target=HealthTarget.MYSQL, is_up=False, detail="old")
    HealthCheck.objects.create(target=HealthTarget.MYSQL, is_up=True, detail="ok")
    HealthCheck.objects.create(target=HealthTarget.REDIS, is_up=True)
    HealthCheck.objects.create(target=HealthTarget.MAIL, is_up=False, detail="down")

    r = boss.get("/api/v1/admin/health/")
    assert r.status_code == 200
    targets = {t["target"]: t for t in r.data["targets"]}
    assert targets[HealthTarget.MYSQL]["is_up"] is True          # newest wins
    assert targets[HealthTarget.PANEL]["is_up"] is None          # no data yet
    assert r.data["overall"] == "degraded"                       # MAIL is down


def test_resources_endpoint_returns_latest_and_series(boss):
    for cpu in (10, 20, 30):
        ResourceStat.objects.create(cpu_percent=cpu, ram_percent=1, disk_percent=1,
                                    net_in=cpu, net_out=cpu, bandwidth_used=0)
    r = boss.get("/api/v1/admin/resources/")
    assert r.data["latest"]["cpu_percent"] == 30
    assert [s["cpu_percent"] for s in r.data["series"]] == [10, 20, 30]


def test_backups_list_and_trigger(boss):
    BackupLog.objects.create(filename="a.sql.gz", size=10, status=BackupStatus.OK, sent_to_telegram=True)
    r = boss.get("/api/v1/admin/backups/")
    assert r.data["results"][0]["filename"] == "a.sql.gz"

    run = boss.post("/api/v1/admin/backups/run/")
    assert run.status_code == 202


def test_monitoring_requires_permission(staff_client, perms):
    weak = make_staff("weak", ["users.view"], perms)
    assert staff_client(weak).get("/api/v1/admin/health/").status_code == 403


def test_dashboard_includes_health_and_resources(boss):
    HealthCheck.objects.create(target=HealthTarget.MYSQL, is_up=True)
    ResourceStat.objects.create(cpu_percent=42, ram_percent=1, disk_percent=1,
                                net_in=0, net_out=0, bandwidth_used=0)
    r = boss.get("/api/v1/admin/dashboard/")
    assert r.data["health"]["up"] == 1
    assert r.data["resources"]["cpu_percent"] == 42


def test_monitoring_snapshot_has_storage(boss, tmp_path, monkeypatch):
    from apps.telegram import backup as backup_mod

    monkeypatch.setattr(backup_mod, "BACKUP_DIR", tmp_path)
    r = boss.get("/api/v1/admin/monitoring/")
    assert r.status_code == 200
    st = r.data["storage"]
    assert st["disk"]["total"] > 0 and st["retention_days"] == 2
    assert st["backups"]["db_count"] == 0 and st["last_cleanup"] is None


def test_monitoring_snapshot_has_disk_watch(boss, tmp_path, monkeypatch):
    import json

    from apps.telegram import backup as backup_mod

    monkeypatch.setattr(backup_mod, "BACKUP_DIR", tmp_path)
    r = boss.get("/api/v1/admin/monitoring/")
    dw = r.data["disk_watch"]
    assert dw["warn_percent"] == 80.0 and dw["crit_percent"] == 90.0 and dw["report"] is None
    (tmp_path / ".disk-report.json").write_text(json.dumps({
        "generated_at": "2026-10-28T03:17:00Z", "disk": {"percent": 60},
        "items": [{"label": "mysql-binlogs", "path": "/x", "bytes": 5}]}))
    dw = boss.get("/api/v1/admin/monitoring/").data["disk_watch"]
    assert dw["report"]["items"][0]["label"] == "mysql-binlogs"
