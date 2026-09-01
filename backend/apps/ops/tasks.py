import logging
import os
import time
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.utils import timezone

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
    """Delete backup files (and their logs) older than BACKUP_RETENTION_DAYS."""
    from apps.ops.models import BackupLog
    from apps.telegram.backup import BACKUP_DIR

    cutoff = timezone.now() - timezone.timedelta(days=settings.BACKUP_RETENTION_DAYS)
    removed = 0
    for entry in BackupLog.objects.filter(created_at__lt=cutoff):
        path = Path(BACKUP_DIR) / entry.filename
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:  # noqa: BLE001
            log.warning("prune: could not delete %s: %s", path, exc)
        entry.delete()
        removed += 1
    return {"pruned": removed}


@shared_task
def reconcile_backup_schedule_task():
    from .schedule import reconcile_backup_schedule

    return reconcile_backup_schedule()
