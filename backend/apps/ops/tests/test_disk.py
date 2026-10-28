"""v1.25.2 disk protection: alert levels, repeat / recovery, daily host report."""
import json
from datetime import datetime, timedelta, timezone as tz

import pytest
from django.core.cache import cache

from apps.ops import disk

pytestmark = pytest.mark.django_db
GB = 1024 ** 3


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    cache.delete(disk.STATE_KEY)
    disk._mem_state.clear()
    sent = []
    monkeypatch.setattr(disk, "send", lambda text: sent.append(text) or 1)
    return sent


def _u(pct):
    return {"total": 100 * GB, "used": pct * GB, "free": (100 - pct) * GB, "percent": float(pct)}


def test_levels_with_hysteresis():
    assert disk.level_for(79.9, 0, 80, 90) == 0
    assert disk.level_for(80, 0, 80, 90) == 1
    assert disk.level_for(90, 1, 80, 90) == 2
    assert disk.level_for(78, 1, 80, 90) == 1      # stays until below 77
    assert disk.level_for(76.9, 1, 80, 90) == 0


def test_alert_at_80_then_90_repeat_and_recovery(_clean):
    sent = _clean
    t = 1_000_000.0
    assert disk.check_disk_alert(t, _u(70))["sent"] == 0
    assert disk.check_disk_alert(t + 60, _u(81))["sent"] == 1 and "WARNING" in sent[-1]
    assert disk.check_disk_alert(t + 120, _u(82))["sent"] == 0           # no spam
    assert disk.check_disk_alert(t + 180, _u(91))["sent"] == 1 and "CRITICAL" in sent[-1]
    assert disk.check_disk_alert(t + 600, _u(92))["sent"] == 0
    assert disk.check_disk_alert(t + 180 + 3600, _u(92))["sent"] == 1     # hourly while critical
    assert disk.check_disk_alert(t + 9000, _u(60))["sent"] == 1 and "normal" in sent[-1]
    assert len(sent) == 4


def test_alert_still_works_when_redis_refuses_writes(_clean, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("MISCONF")
    monkeypatch.setattr(disk.cache, "set", boom)
    monkeypatch.setattr(disk.cache, "get", boom)
    assert disk.check_disk_alert(1.0, _u(95))["sent"] == 1
    assert disk.check_disk_alert(2.0, _u(95))["sent"] == 0              # in-process state


def test_thresholds_come_from_settings(_clean):
    from apps.settings_app.utils import set_setting

    set_setting("disk_alert_warn_percent", 70, "int")
    set_setting("disk_alert_crit_percent", 85, "int")
    assert disk.thresholds() == (70.0, 85.0)
    assert disk.check_disk_alert(1.0, _u(72))["level"] == 1


def _write(d, name, when, items):
    (d / name).write_text(json.dumps({"generated_at": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                      "disk": _u(50), "items": items}))


def test_report_growth_staleness_and_daily_message(tmp_path, monkeypatch, _clean):
    sent = _clean
    monkeypatch.setattr("apps.ops.retention.backup_dir", lambda: tmp_path)
    monkeypatch.setattr(disk, "disk_usage", lambda: _u(50))
    now = datetime(2026, 10, 28, 4, 0, tzinfo=tz.utc)
    assert disk.report_snapshot(now)["report"] is None
    assert disk.daily_report(now)["reasons"] and "missing" in sent[-1]

    _write(tmp_path, ".disk-report.prev.json", now - timedelta(days=1, hours=1),
           [{"label": "mysql-binlogs", "bytes": 10 * GB}, {"label": "/var/log", "bytes": GB}])
    _write(tmp_path, ".disk-report.json", now - timedelta(hours=1),
           [{"label": "mysql-binlogs", "bytes": 13 * GB}, {"label": "/var/log", "bytes": GB}])
    snap = disk.report_snapshot(now)
    assert not snap["stale"]
    rows = {i["label"]: i for i in snap["report"]["items"]}
    assert rows["mysql-binlogs"]["growth_per_day"] == 3 * GB and rows["/var/log"]["growth_per_day"] == 0
    res = disk.daily_report(now)
    assert res["sent"] == 1 and "mysql-binlogs" in sent[-1]

    assert disk.report_snapshot(now + timedelta(days=2))["stale"]

