"""Blu collector settings from the panel (Super Admin): stored in DB, override .env, no restart."""
import pytest
from django_celery_beat.models import PeriodicTask

from apps.ops.schedule import BLU_SERVICE_TASK, reconcile_blu_service_schedule
from apps.payments_sms.blu import blu_settings, stale_after
from apps.payments_sms.matching import _blu_grace
from apps.payments_sms.tests.test_blu import staff_client

pytestmark = pytest.mark.django_db


def test_env_values_until_the_panel_saves(settings):
    settings.BLU_STALE_MINUTES = 360
    settings.BLU_LATE_GRACE_MINUTES = 30
    s = blu_settings()
    assert s["stale_minutes"] == 360 and s["late_grace_minutes"] == 30 and s["ssh_check_minutes"] == 5
    assert s["source"] == {"stale_minutes": "env", "late_grace_minutes": "env"} and s["collector_poll_seconds"] == 45


def test_super_admin_saves_and_they_apply_at_once(settings):
    settings.BLU_STALE_MINUTES = 360
    reconcile_blu_service_schedule()
    c = staff_client("super", "boss")
    r = c.put("/api/v1/admin/settings/", {"blu_ssh_check_minutes": 2, "blu_stale_minutes": 90,
                                          "blu_late_grace_minutes": 0}, format="json")
    assert r.status_code == 200, r.content
    assert stale_after().total_seconds() == 90 * 60 and _blu_grace().total_seconds() == 0
    task = PeriodicTask.objects.get(name=BLU_SERVICE_TASK)
    assert task.interval.every == 2 and task.enabled
    col = c.get("/api/v1/admin/payments/blu-transactions/").json()["collector"]
    assert col["settings"]["stale_minutes"] == 90 and col["settings"]["source"]["stale_minutes"] == "panel"
    assert col["stale_minutes"] == 90
    # minimum 1 minute for the SSH check
    c.put("/api/v1/admin/settings/", {"blu_ssh_check_minutes": 0}, format="json")
    assert PeriodicTask.objects.get(name=BLU_SERVICE_TASK).interval.every == 1


def test_seed_keeps_the_panel_interval():
    from django.core.management import call_command

    c = staff_client("super", "boss")
    c.put("/api/v1/admin/settings/", {"blu_ssh_check_minutes": 7}, format="json")
    call_command("seed")
    assert PeriodicTask.objects.get(name=BLU_SERVICE_TASK).interval.every == 7


def test_rounded_percent_is_validated():
    c = staff_client("super", "boss")
    assert c.put("/api/v1/admin/settings/", {"rounded_max_percent": "abc"}, format="json").status_code == 400
    assert c.put("/api/v1/admin/settings/", {"rounded_max_percent": "11"}, format="json").status_code == 400
    r = c.put("/api/v1/admin/settings/", {"rounded_max_percent": "0.5"}, format="json")
    assert {x["key"]: x["value"] for x in r.json()["settings"]}["rounded_max_percent"] == "0.5"
