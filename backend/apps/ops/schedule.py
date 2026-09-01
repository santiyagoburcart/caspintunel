"""Keep celery-beat PeriodicTask intervals in step with runtime settings."""
from __future__ import annotations

import logging

log = logging.getLogger("caspintunel")


def reconcile_backup_schedule() -> dict:
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    from apps.settings_app.utils import get_setting

    minutes = max(int(get_setting("backup_interval_minutes", 1440) or 1440), 1)
    task = PeriodicTask.objects.filter(name="ops: database backup").first()
    if not task:
        return {"skipped": "backup task not registered yet"}
    if task.interval and task.interval.every == minutes and task.interval.period == IntervalSchedule.MINUTES:
        return {"unchanged": minutes}
    schedule, _ = IntervalSchedule.objects.get_or_create(every=minutes, period=IntervalSchedule.MINUTES)
    task.interval = schedule
    task.save(update_fields=["interval"])
    log.info("backup schedule reconciled to every %s min", minutes)
    return {"updated_to": minutes}
