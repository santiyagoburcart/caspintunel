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
    from .disk import check_disk_alert
    from .resources import sample_resources

    # the disk alert goes first: it must work even when the DB / Redis can't write
    try:
        check_disk_alert()
    except Exception:  # noqa: BLE001
        logging.getLogger("caspintunel").exception("disk alert check failed")
    stat = sample_resources()
    # v1.39.0: per-container memory / swap / pressure / load (host report, apps/ops/containers.py)
    try:
        from .containers import check as check_containers

        check_containers()
    except Exception:  # noqa: BLE001
        logging.getLogger("caspintunel").exception("container memory check failed")
    return {"cpu": stat.cpu_percent, "ram": stat.ram_percent, "disk": stat.disk_percent}


@shared_task
def service_alerts_task():
    """Pre-expiry warnings (apps.crm.retention: configurable thresholds, quiet hours,
    one per threshold per service period, renew button). The old fixed alert
    (ops.alerts.run_service_alerts) only runs when the retention warnings are off."""
    from apps.crm.retention import run_warnings, setting
    from apps.tenancy.context import for_each_tenant

    from .alerts import run_service_alerts

    def one_store():                                 # v1.50: every store's customers (through its own bot / name)
        return run_warnings() if setting("retention_warnings_enabled") else run_service_alerts()

    return for_each_tenant(one_store, name="service_alerts")


@shared_task
def disk_report_task():
    """Daily: the host's biggest folders / volumes report + growth (apps/ops/disk.py)."""
    from .disk import daily_report

    return daily_report()


@shared_task
def prune_backups_task():
    """Local backup retention (apps/ops/retention.py). Name kept for beat."""
    from .retention import run_cleanup

    return run_cleanup()


@shared_task
def reconcile_backup_schedule_task():
    from .schedule import reconcile_backup_schedule

    return reconcile_backup_schedule()


@shared_task(ignore_result=True)
def ssl_check_task(alert: bool = True):
    """v1.57 «گواهی‌های SSL» (ops/ssl_certs.py): daily + «بررسی الان» on Monitoring."""
    from .ssl_certs import run

    return run(alert=alert)
