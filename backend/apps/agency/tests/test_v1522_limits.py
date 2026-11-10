"""v1.52.2 — limit changes after the farzin3 case (2026-11-10).

B. A limit change through our panel that leaves room ends an enforcement block AT ONCE (enable on PasarGuard, flag cleared) —
   also for an admin made unlimited (the stale «محدود‌شده» case); no room → nothing changes; a failed enable never fails the
   limit change. PAMP's enforcement code is untouched (test_golden).
C. The preview warns when the new limit leaves < 5 % of it or < 50 GB above current usage.
D. The preview flags an unlimited admin without an earlier limit: the whole new limit is charged.
+  Daily Telegram summary of admins ≥ 95 % (silent, ours only, nothing when none), beat entry 10:00 Tehran made once by seed.
"""
import json

import pytest
import responses
from django.core.management import call_command

from apps.agency import ledger
from apps.agency.models import PanelAdmin
from apps.agency.tests.test_agency_api import client
from apps.common.models import AuditLog
from apps.panel.models import Panel
from apps.settings_app.models import ValueType
from apps.settings_app.utils import set_setting

pytestmark = pytest.mark.django_db
GB = 1024 ** 3
BASE = "https://sigma.test"


@pytest.fixture
def boss():
    Panel.objects.create(name="sigma", base_url=BASE, admin_username="u", admin_password_enc="p", is_active=True)
    set_setting("agency_sync_enabled", True, ValueType.BOOL)
    return client(is_superadmin=True)


def _blocked(name="farz", limit_gb=100, used_gb=100, **kw):
    ledger.set_price(name, 2000, ledger.today())
    return PanelAdmin.objects.create(username=name, has_data_limit=limit_gb > 0, admin_limit_bytes=limit_gb * GB,
                                     total_user_used=used_gb * GB, status=kw.pop("status", "disabled"), is_active=False,
                                     pamp_blocked=True, **kw)


def _panel(enable_status=200):
    responses.add("POST", f"{BASE}/api/admin/token", json={"access_token": "t"})
    responses.add("PUT", f"{BASE}/api/admin/farz", json={})                      # the limit
    responses.add("PUT", f"{BASE}/api/admin/farz", json={}, status=enable_status)  # the enable


def _puts():
    return [json.loads(c.request.body) for c in responses.calls if c.request.method == "PUT"]


# ------------------------------------------------------------------ B
@responses.activate
def test_a_raise_with_room_ends_the_block_at_once(boss):
    _blocked()
    _panel()
    r = boss.post("/api/v1/admin/agency/admins/farz/set-limit/", {"action": "add", "value_gb": 50}, format="json")
    assert r.status_code == 200, r.content
    assert {"status": "active"} in _puts()
    a = PanelAdmin.objects.get(username="farz")
    assert not a.pamp_blocked and a.pamp_blocked_at is None and a.status == "active" and a.is_active
    assert AuditLog.objects.filter(action="agency.enforcement_released", detail__admin="farz").exists()


@responses.activate
def test_a_raise_without_room_keeps_the_block(boss):
    _blocked(limit_gb=100, used_gb=180)
    _panel()
    assert boss.post("/api/v1/admin/agency/admins/farz/set-limit/", {"action": "add", "value_gb": 50},
                     format="json").status_code == 200
    assert {"status": "active"} not in _puts()
    assert PanelAdmin.objects.get(username="farz").pamp_blocked


@responses.activate
def test_removing_the_limit_never_leaves_a_stale_limited_flag(boss):
    _blocked()
    _panel()
    r = boss.post("/api/v1/admin/agency/admins/farz/remove-limit/", {}, format="json")
    assert r.status_code == 200, r.content
    a = PanelAdmin.objects.get(username="farz")
    assert not a.has_data_limit and not a.pamp_blocked and a.status_code == "active"


@responses.activate
def test_a_failed_enable_never_fails_the_limit_change(boss):
    _blocked()
    _panel(enable_status=500)
    r = boss.post("/api/v1/admin/agency/admins/farz/set-limit/", {"action": "add", "value_gb": 50}, format="json")
    assert r.status_code == 200, r.content
    a = PanelAdmin.objects.get(username="farz")
    assert a.admin_limit_bytes == 150 * GB and a.pamp_blocked                      # the next sync retries the unblock
    assert AuditLog.objects.filter(action="agency.enforcement_release_failed").exists()


def test_release_does_nothing_for_an_admin_that_is_not_blocked(boss):
    from apps.agency.release import release_if_room

    PanelAdmin.objects.create(username="free", has_data_limit=True, admin_limit_bytes=10 * GB, total_user_used=GB)
    assert release_if_room("free") is None                                        # no PasarGuard call at all


# ------------------------------------------------------------------ C + D (preview)
def test_preview_warns_about_little_headroom(boss):
    from apps.agency.actions import low_headroom

    ledger.set_price("farz", 2000, ledger.today())
    PanelAdmin.objects.create(username="farz", has_data_limit=False, admin_limit_bytes=0, total_user_used=11584 * GB)
    p = boss.post("/api/v1/admin/agency/admins/farz/set-limit/preview/", {"action": "set", "value_gb": 11600},
                  format="json").json()
    assert p["low_headroom"] is True and p["used_bytes"] == 11584 * GB
    assert low_headroom(10000 * GB, 9600 * GB) is True                            # 400 GB < 5 % of 10 TB
    assert low_headroom(1000 * GB, 940 * GB) is False                             # 60 GB ≥ 50 GB and ≥ 5 %
    assert low_headroom(500 * GB, 460 * GB) is True                               # 40 GB < 50 GB
    assert low_headroom(0, 999 * GB) is False                                     # unlimited


def test_preview_shows_the_full_charge_for_an_unlimited_admin_without_an_earlier_limit(boss):
    ledger.set_price("farz", 2000, ledger.today())
    PanelAdmin.objects.create(username="farz", has_data_limit=False, admin_limit_bytes=0, total_user_used=11584 * GB)
    p = boss.post("/api/v1/admin/agency/admins/farz/set-limit/preview/", {"action": "set", "value_gb": 11600},
                  format="json").json()
    assert p["full_charge"] is True and p["charge"]["amount"] == 11600 * 2000
    PanelAdmin.objects.filter(username="farz").update(last_limit_bytes=11000 * GB)
    p = boss.post("/api/v1/admin/agency/admins/farz/set-limit/preview/", {"action": "set", "value_gb": 11600},
                  format="json").json()
    assert p["full_charge"] is False and p["charge"]["amount"] == 600 * 2000      # charged from the last limit


# ------------------------------------------------------------------ daily summary
def test_daily_summary_lists_admins_at_95_percent_or_more(boss, monkeypatch):
    from apps.agency import tasks
    from apps.common import staff_alert

    sent = []
    monkeypatch.setattr(staff_alert, "alert_staff", lambda text, **kw: sent.append((text, kw)) or 1)
    PanelAdmin.objects.create(username="calm", has_data_limit=True, admin_limit_bytes=100 * GB, total_user_used=50 * GB)
    PanelAdmin.objects.create(username="unl", has_data_limit=False, total_user_used=900 * GB)
    assert tasks.near_limit_summary_task() == {"sent": 0, "admins": 0}            # nobody close → nothing sent
    PanelAdmin.objects.create(username="close", has_data_limit=True, admin_limit_bytes=100 * GB, total_user_used=96 * GB)
    _blocked(name="over", limit_gb=100, used_gb=100, status="active")
    out = tasks.near_limit_summary_task()
    assert out == {"sent": 1, "admins": 2}
    text, kw = sent[0]
    assert text.index("over") < text.index("close") and "calm" not in text and "unl" not in text
    assert "96.0%" in text and "4.0 GB" in text and "محدود" in text
    assert kw["perm"] == "agency.manage" and kw["silent"] is True and kw["platform"] is True
    set_setting("agency_sync_enabled", False, ValueType.BOOL)
    assert tasks.near_limit_summary_task()["skipped"] == "sync disabled"


def test_seed_creates_the_daily_entry_once_and_keeps_staff_edits(boss):
    from django_celery_beat.models import PeriodicTask

    call_command("seed")
    t = PeriodicTask.objects.get(name="agency: near-limit summary")
    assert t.task == "apps.agency.tasks.near_limit_summary_task" and t.crontab.hour == "10"
    assert str(t.crontab.timezone) == "Asia/Tehran"
    t.enabled = False
    t.save()
    call_command("seed")
    assert PeriodicTask.objects.get(name="agency: near-limit summary").enabled is False
