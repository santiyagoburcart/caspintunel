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


BLU_SERVICE_TASK = "payments: Blu collector service check (SSH)"
AUTO_PURGE_TASK = "accounts: auto-purge deleted users (daily)"


def reconcile_blu_service_schedule() -> dict:
    """The SSH health check runs every `blu_ssh_check_minutes` (Blu tab, Super Admin; default 5).
    Creates the PeriodicTask when missing. celery-beat's DatabaseScheduler notices the change
    on its own — no restart."""
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    from apps.settings_app.utils import get_setting

    minutes = max(int(get_setting("blu_ssh_check_minutes", 5) or 5), 1)
    schedule, _ = IntervalSchedule.objects.get_or_create(every=minutes, period=IntervalSchedule.MINUTES)
    task = PeriodicTask.objects.filter(name=BLU_SERVICE_TASK).first()
    if task is None:
        PeriodicTask.objects.create(name=BLU_SERVICE_TASK, task="apps.payments_sms.tasks.blu_service_check_task",
                                    interval=schedule, kwargs="{}", enabled=True)
        return {"created": minutes}
    if task.interval_id == schedule.id and task.enabled:
        return {"unchanged": minutes}
    task.interval = schedule
    task.enabled = True
    task.save(update_fields=["interval", "enabled"])
    log.info("Blu service check reconciled to every %s min", minutes)
    return {"updated_to": minutes}


def ensure_auto_purge_schedule() -> None:
    """Daily beat entry for the deleted-users auto-purge. The task itself does nothing while
    the setting `deleted_purge_enabled` is off (default)."""
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    daily, _ = IntervalSchedule.objects.get_or_create(every=1440, period=IntervalSchedule.MINUTES)
    PeriodicTask.objects.update_or_create(
        name=AUTO_PURGE_TASK,
        defaults={"task": "apps.accounts.tasks.auto_purge_deleted_users_task", "interval": daily,
                  "kwargs": "{}", "enabled": True},
    )
