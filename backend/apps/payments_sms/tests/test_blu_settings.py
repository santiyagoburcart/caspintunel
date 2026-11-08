"""Blu collector settings from the panel (Super Admin): stored in DB, override .env, no restart."""
import pytest
from django_celery_beat.models import PeriodicTask

from apps.ops.schedule import BLU_SERVICE_TASK, reconcile_blu_service_schedule
from apps.payments_sms.blu import blu_settings
from apps.payments_sms.blu_service import poll_stale_minutes
from apps.payments_sms.matching import _blu_grace
from apps.payments_sms.tests.test_blu import staff_client

pytestmark = pytest.mark.django_db


def test_env_values_until_the_panel_saves(settings):
    settings.BLU_LATE_GRACE_MINUTES = 30
    s = blu_settings()
    assert s["poll_stale_minutes"] == 10 and s["late_grace_minutes"] == 30 and s["ssh_check_minutes"] == 5
    assert s["source"] == {"late_grace_minutes": "env"} and s["collector_poll_seconds"] == 45


def test_super_admin_saves_and_they_apply_at_once(settings):
    reconcile_blu_service_schedule()
    c = staff_client("super", "boss")
    r = c.put("/api/v1/admin/settings/", {"blu_ssh_check_minutes": 2, "blu_poll_stale_minutes": 15,
                                          "blu_late_grace_minutes": 0}, format="json")
    assert r.status_code == 200, r.content
    assert poll_stale_minutes() == 15 and _blu_grace().total_seconds() == 0
    task = PeriodicTask.objects.get(name=BLU_SERVICE_TASK)
    assert task.interval.every == 2 and task.enabled
    col = c.get("/api/v1/admin/payments/blu-transactions/").json()["collector"]
    assert col["settings"]["poll_stale_minutes"] == 15 and col["settings"]["source"]["late_grace_minutes"] == "panel"
    # minimum 1 minute for the SSH check
    c.put("/api/v1/admin/settings/", {"blu_ssh_check_minutes": 0}, format="json")
    assert PeriodicTask.objects.get(name=BLU_SERVICE_TASK).interval.every == 1


def test_seed_keeps_the_panel_interval():
    from django.core.management import call_command

    c = staff_client("super", "boss")
    c.put("/api/v1/admin/settings/", {"blu_ssh_check_minutes": 7}, format="json")
    call_command("seed")
    assert PeriodicTask.objects.get(name=BLU_SERVICE_TASK).interval.every == 7


def test_rounded_tolerance_is_tomans_only():
    """v1.44.1: ± rounded_max_toman (the percent setting is gone)."""
    c = staff_client("super", "boss")
    keys = {x["key"] for x in c.get("/api/v1/admin/settings/").json()["settings"]}
    assert "rounded_max_toman" in keys and "rounded_max_percent" not in keys
    r = c.put("/api/v1/admin/settings/", {"rounded_max_toman": 3000}, format="json")
    assert {x["key"]: x["value"] for x in r.json()["settings"]}["rounded_max_toman"] == 3000
