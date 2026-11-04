"""v1.39.0 container memory watch (apps/ops/containers.py): the host report is parsed, our containers are told apart
from the PasarGuard nodes, alerts fire for a container near its limit, an OOM kill, a restart, sustained swap, memory
pressure and load — each once per 6 h, one "back to normal" line — and the Monitoring snapshot carries it."""
import json
from datetime import datetime, timedelta
from datetime import timezone as dt_tz

import pytest
from django.core.cache import cache

from apps.ops import containers

pytestmark = pytest.mark.django_db
GB, MB = 1024 ** 3, 1024 ** 2
T0 = datetime(2026, 11, 4, 12, 0, tzinfo=dt_tz.utc)


def report(tmp_path, monkeypatch, *, at=T0, web_used=200 * MB, oom=False, restarts=0, swap=500 * MB, psi=0.2, load15=0.9):
    data = {"generated_at": at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "host": {"cpus": 2, "load1": 1, "load5": 1, "load15": load15, "mem_total": 4 * GB, "mem_available": GB,
                     "swap_total": 4 * GB, "swap_used": swap, "psi_some_avg60": psi, "psi_full_avg60": 0},
            "containers": [
                {"name": "caspintunel-web-55", "project": "caspintunel", "service": "web", "cpu": "1.0", "mem_used": web_used,
                 "mem_limit": 640 * MB, "oom_killed": oom, "restarts": restarts, "state": "running", "started_at": "-"},
                {"name": "caspintunel-db-1", "project": "caspintunel", "service": "db", "cpu": "3", "mem_used": 150 * MB,
                 "mem_limit": 640 * MB, "oom_killed": False, "restarts": 0, "state": "running", "started_at": "-"},
                {"name": "hel-cdn1", "project": "hel-cdn1", "service": "node", "cpu": "9", "mem_used": 600 * MB,
                 "mem_limit": 0, "oom_killed": False, "restarts": 0, "state": "running", "started_at": "-"}]}
    (tmp_path / ".container-stats.json").write_text(json.dumps(data))
    from apps.ops import retention

    monkeypatch.setattr(retention, "backup_dir", lambda: tmp_path)


@pytest.fixture
def sent(monkeypatch):
    cache.delete(containers._STATE_KEY)
    out = []
    monkeypatch.setattr(containers, "send", lambda text: out.append(text) or 1)
    return out


def test_snapshot_orders_ours_first_and_marks_others(tmp_path, monkeypatch, sent):
    report(tmp_path, monkeypatch, web_used=320 * MB)
    s = containers.snapshot(T0 + timedelta(minutes=3))
    assert s["report"] and not s["stale"]
    assert [r["service"] for r in s["containers"]] == ["web", "db", "node"]
    assert s["containers"][0]["percent"] == 50.0 and s["containers"][2]["ours"] is False and s["containers"][2]["percent"] is None
    assert containers.snapshot(T0 + timedelta(minutes=30))["stale"] is True


def test_alerts_once_per_problem_and_once_on_recovery(tmp_path, monkeypatch, sent):
    report(tmp_path, monkeypatch)
    assert containers.check(T0)["problems"] == [] and sent == []                 # all fine, first sample stores restarts
    report(tmp_path, monkeypatch, at=T0 + timedelta(minutes=5), web_used=600 * MB, oom=True, restarts=1, psi=12.5, load15=2.6)
    r = containers.check(T0 + timedelta(minutes=5))
    assert set(r["problems"]) == {"mem:web", "oom:web", "restart:web", "psi", "load"} and len(sent) == 1
    assert "web uses 600 MB of its 640 MB" in sent[0] and "OOM" in sent[0] and "hel-cdn1" not in sent[0]
    report(tmp_path, monkeypatch, at=T0 + timedelta(minutes=10), web_used=600 * MB, oom=True, restarts=1, psi=12.5, load15=2.6)
    containers.check(T0 + timedelta(minutes=10))
    assert len(sent) == 1                                                          # same problems: no repeat within 6 h
    report(tmp_path, monkeypatch, at=T0 + timedelta(minutes=15), restarts=1)
    containers.check(T0 + timedelta(minutes=15))
    assert len(sent) == 2 and "back to normal" in sent[1]


def test_swap_alert_only_after_30_minutes_and_stale_report(tmp_path, monkeypatch, sent):
    for minute in (0, 10, 20):
        report(tmp_path, monkeypatch, at=T0 + timedelta(minutes=minute), swap=2 * GB)
        containers.check(T0 + timedelta(minutes=minute))
    assert sent == []                                                              # high, but not for 30 min yet
    report(tmp_path, monkeypatch, at=T0 + timedelta(minutes=31), swap=2 * GB)
    assert containers.check(T0 + timedelta(minutes=31))["problems"] == ["swap"] and "swap in use 2.0 GB" in sent[0]
    # the cron stopped: the report goes stale → one alert about the report itself
    assert containers.check(T0 + timedelta(minutes=60))["problems"] == ["report"]


def test_monitoring_api_carries_the_snapshot(tmp_path, monkeypatch, sent):
    from apps.payments_sms.tests.test_blu import staff_client

    report(tmp_path, monkeypatch, at=datetime.now(dt_tz.utc))
    d = staff_client("super", "boss").get("/api/v1/admin/monitoring/").json()
    assert d["containers"]["report"] is True and d["containers"]["containers"][0]["service"] == "web"
