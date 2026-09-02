from django.db import models

# The audit log lives in apps.common (AuditLog + write_audit); ops reads it.
from apps.common.models import AuditLog  # noqa: F401  (re-exported for discoverability)


class BackupStatus(models.TextChoices):
    OK = "ok", "OK"
    FAILED = "failed", "Failed"


class BackupLog(models.Model):
    """data-model · Module 9 · `backup_log`."""

    filename = models.CharField(max_length=255)
    size = models.BigIntegerField(default=0, help_text="bytes")
    status = models.CharField(max_length=8, choices=BackupStatus.choices, default=BackupStatus.OK)
    sent_to_telegram = models.BooleanField(default=False)
    error = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "backup_log"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.filename


class HealthTarget(models.TextChoices):
    SITE = "site", "Site"
    MYSQL = "mysql", "MySQL"
    REDIS = "redis", "Redis"
    CELERY_WORKER = "celery_worker", "Celery worker"
    CELERY_BEAT = "celery_beat", "Celery beat"
    BOT_SALES = "bot_sales", "Sales bot"
    BOT_BACKUP = "bot_backup", "Backup bot"
    PANEL = "panel", "Panel"
    MAIL = "mail", "Mail"


class HealthCheck(models.Model):
    """data-model · Module 9 · `health_check`."""

    target = models.CharField(max_length=16, choices=HealthTarget.choices, db_index=True)
    # multi-panel: PANEL checks get one row per panel + one aggregate row
    # (panel = NULL). Other targets always have panel = NULL.
    panel = models.ForeignKey(
        "panel.Panel", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="health_checks",
    )
    is_up = models.BooleanField(default=False)
    latency_ms = models.IntegerField(null=True, blank=True)
    detail = models.CharField(max_length=255, blank=True)
    checked_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "health_check"
        ordering = ("-checked_at",)

    def __str__(self) -> str:
        return f"{self.target}: {'up' if self.is_up else 'down'}"


class ResourceStat(models.Model):
    """data-model · Module 9 · `resource_stat`."""

    cpu_percent = models.FloatField(default=0)
    ram_percent = models.FloatField(default=0)
    disk_percent = models.FloatField(default=0)
    net_in = models.BigIntegerField(default=0)
    net_out = models.BigIntegerField(default=0)
    bandwidth_used = models.BigIntegerField(default=0)
    sampled_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "resource_stat"
        ordering = ("-sampled_at",)

    def __str__(self) -> str:
        return f"resources @ {self.sampled_at:%Y-%m-%d %H:%M}"
