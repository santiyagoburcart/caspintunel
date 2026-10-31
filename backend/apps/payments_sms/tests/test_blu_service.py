"""Collector service check over SSH (blu_service.py): fixed read-only command, alerts only
for inactive / 3 SSH failures in a row / repeated errors, one "back online". No real SSH:
subprocess.run is replaced by a fake."""
import subprocess

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Staff
from apps.adminpanel.tokens import issue_tokens
from apps.payments_sms import blu_service
from apps.payments_sms.blu_service import check_service, remote_command
from apps.payments_sms.models import BluCollector

pytestmark = pytest.mark.django_db

OK_JOURNAL = ("2026-10-31T13:41:30+0000 host node[1]: blu-collector started\n"
              "2026-10-31T13:41:31+0000 host node[1]: delivered 4 item(s); outbox now 0\n")
ERR = "2026-10-31T13:50:00+0000 host node[1]: push failed: HTTP 403 card 6037991234565440 secret=abc\n"


@pytest.fixture
def fake(monkeypatch, settings):
    from apps.common import staff_alert
    from apps.notifications import live

    settings.BLU_SSH_HOST = "iran"
    settings.BLU_COLLECTOR_SERVICE = "blu-collector.service"
    settings.BLU_ERROR_REPEAT = 3
    state = {"out": "active\n---JOURNAL---\n" + OK_JOURNAL, "rc": 0, "err": "", "calls": [], "raise": None}
    alerts, events = [], []

    def run(argv, **kw):
        state["calls"].append(argv)
        if state["raise"]:
            raise state["raise"]
        return subprocess.CompletedProcess(argv, state["rc"], stdout=state["out"], stderr=state["err"])

    monkeypatch.setattr(blu_service.subprocess, "run", run)
    monkeypatch.setattr(staff_alert, "alert_staff", lambda text, **kw: alerts.append(text) or 1)
    monkeypatch.setattr(live, "push_payments_event", lambda e, **d: events.append((e, d)))
    state["alerts"], state["events"] = alerts, events
    return state


def set_out(fake, state="active", journal=OK_JOURNAL, rc=0):
    fake.update(out=f"{state}\n---JOURNAL---\n{journal}", rc=rc, err="")


def test_disabled_without_host(fake, settings):
    settings.BLU_SSH_HOST = ""
    assert check_service() == "disabled" and fake["calls"] == []


def test_runs_only_the_fixed_read_only_command(fake):
    assert check_service() == "ok"
    argv = fake["calls"][0]
    assert argv[0] == "ssh" and argv[-2] == "iran" and argv[-1] == remote_command("blu-collector.service")
    assert argv[-1] == ("systemctl is-active blu-collector.service; echo ---JOURNAL---; "
                        "journalctl -u blu-collector.service --since -10min --no-pager -o short-iso -q")
    assert "BatchMode=yes" in argv and "StrictHostKeyChecking=yes" in argv
    c = BluCollector.get()
    assert c.svc_state == "active" and c.svc_checked_at and c.svc_error_count == 0 and not fake["alerts"]


def test_bad_service_name_is_refused(fake, settings):
    settings.BLU_COLLECTOR_SERVICE = "x; rm -rf /"
    with pytest.raises(ValueError):
        check_service()
    assert fake["calls"] == []


def test_inactive_alerts_once_then_recovers(fake):
    set_out(fake, "inactive", rc=3)
    assert check_service() == "alert:inactive"
    assert check_service() == "inactive"                   # still down: no second message
    assert len(fake["alerts"]) == 1 and "inactive" in fake["alerts"][0]
    set_out(fake, "active")
    assert check_service() == "recovered"
    assert check_service() == "ok"
    assert len(fake["alerts"]) == 2 and "healthy again" in fake["alerts"][1]
    assert [d["ok"] for e, d in fake["events"] if e == "blu_service"] == [False, True]


def test_ssh_failures_alert_only_on_the_third_in_a_row(fake):
    fake.update(rc=255, out="", err="ssh: connect to host 185.0.0.1 port 22: Connection timed out")
    assert check_service() == "ssh_failed"
    assert check_service() == "ssh_failed"
    assert not fake["alerts"]
    assert check_service() == "alert:ssh"
    c = BluCollector.get()
    assert c.ssh_failures == 3 and "timed out" in c.ssh_error and len(fake["alerts"]) == 1
    set_out(fake)                                          # SSH works again
    assert check_service() == "recovered" and BluCollector.get().ssh_failures == 0


def test_two_ssh_failures_then_success_never_alerts(fake):
    fake["raise"] = subprocess.TimeoutExpired("ssh", 40)
    check_service(); check_service()
    fake["raise"] = None
    set_out(fake)
    assert check_service() == "ok" and not fake["alerts"]


def test_repeated_errors_alert_with_masked_last_line(fake):
    set_out(fake, journal=OK_JOURNAL + ERR)
    assert check_service() == "ok"                          # one error is not "repeating"
    set_out(fake, journal=ERR * 3)
    assert check_service() == "alert:errors"
    c = BluCollector.get()
    assert c.svc_error_count == 3
    assert "6037991234565440" not in c.svc_error_line and "603799******5440" in c.svc_error_line
    assert "secret=***" in c.svc_error_line
    assert "6037991234565440" not in fake["alerts"][0]


def test_tab_shows_service_health(fake):
    set_out(fake, journal=ERR)
    check_service()
    s = Staff(username="boss", is_superadmin=True); s.set_password("x-Str0ng!"); s.save()
    c = APIClient(); c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    svc = c.get("/api/v1/admin/payments/blu-transactions/").json()["collector"]["service"]
    assert svc["configured"] is True and svc["state"] == "active" and svc["checked_at"]
    assert "HTTP 403" in svc["error_line"] and svc["alert"] == ""
