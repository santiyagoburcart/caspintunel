import logging

from celery import shared_task

log = logging.getLogger("caspintunel")


@shared_task
def health_check_task():
    from .health import run_health_checks

    results = run_health_checks()
    return {"checked": len(results), "down": [r["target"] for r in results if not r["is_up"]]}


@shared_task
def resource_sample_task():
    from .resources import sample_resources

    stat = sample_resources()
    return {"cpu": stat.cpu_percent, "ram": stat.ram_percent, "disk": stat.disk_percent}


@shared_task
def service_alerts_task():
    """Pre-expiry warnings (apps.crm.retention: configurable thresholds, quiet hours,
    one per threshold per service period, renew button). The old fixed alert
    (ops.alerts.run_service_alerts) only runs when the retention warnings are off."""
    from apps.crm.retention import run_warnings, setting

    if setting("retention_warnings_enabled"):
        return run_warnings()
    from .alerts import run_service_alerts

    return run_service_alerts()


@shared_task
def prune_backups_task():
    """Local backup retention (apps/ops/retention.py). Name kept for beat."""
    from .retention import run_cleanup

    return run_cleanup()


@shared_task
def reconcile_backup_schedule_task():
    from .schedule import reconcile_backup_schedule

    return reconcile_backup_schedule()
