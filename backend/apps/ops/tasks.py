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
