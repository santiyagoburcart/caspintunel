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


def reconcile_sync_schedule() -> dict:
    """Keep the "panel: sync all services" beat interval in step with the
    service_sync_interval_minutes setting — creates the PeriodicTask if it
    doesn't exist yet (e.g. this deploy never ran `manage.py seed`)."""
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    from apps.settings_app.utils import get_setting

    minutes = max(int(get_setting("service_sync_interval_minutes", 60) or 60), 1)
    schedule, _ = IntervalSchedule.objects.get_or_create(every=minutes, period=IntervalSchedule.MINUTES)
    task = PeriodicTask.objects.filter(name="panel: sync all services").first()
    if task:
        if task.interval_id == schedule.id and task.enabled:
            return {"unchanged": minutes}
        task.interval = schedule
        task.enabled = True
        task.save(update_fields=["interval", "enabled"])
    else:
        PeriodicTask.objects.create(
            name="panel: sync all services",
            task="apps.panel.tasks.sync_all_services",
            interval=schedule,
            kwargs="{}",
            enabled=True,
        )
    log.info("service sync schedule reconciled to every %s min", minutes)
    return {"updated_to": minutes}
