import pytest
from django_celery_beat.models import IntervalSchedule, PeriodicTask

from apps.ops.schedule import reconcile_backup_schedule
from apps.settings_app.utils import set_setting

pytestmark = pytest.mark.django_db


def _backup_task():
    sched, _ = IntervalSchedule.objects.get_or_create(every=1440, period=IntervalSchedule.MINUTES)
    return PeriodicTask.objects.create(
        name="ops: database backup", task="apps.telegram.tasks.run_backup_task", interval=sched
    )


def test_reconcile_updates_interval_from_setting():
    task = _backup_task()
    set_setting("backup_interval_minutes", "360", "int")

    reconcile_backup_schedule()
    task.refresh_from_db()
    assert task.interval.every == 360


def test_setting_save_signal_reconciles_automatically():
    task = _backup_task()
    set_setting("backup_interval_minutes", "120", "int")  # post_save signal fires
    task.refresh_from_db()
    assert task.interval.every == 120


def test_reconcile_is_noop_when_already_aligned():
    task = _backup_task()
    set_setting("backup_interval_minutes", "1440", "int")
    assert reconcile_backup_schedule() == {"unchanged": 1440}
