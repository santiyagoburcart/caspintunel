from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base: created_at / updated_at on every domain table."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditLog(models.Model):
    """
    Immutable record of a staff action. Written by apps.ops / admin views.
    Full population happens as staff features land; the table exists from phase 1.
    """

    staff_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    staff_label = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=100, db_index=True)
    target_type = models.CharField(max_length=100, blank=True)
    target_id = models.BigIntegerField(null=True, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "audit_log"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.action} by {self.staff_label or self.staff_id} @ {self.created_at:%Y-%m-%d %H:%M}"


def write_audit(*, action, staff=None, target=None, detail=None, ip=None):
    """Convenience helper; safe to call from anywhere."""
    staff_id = getattr(staff, "id", None)
    staff_label = getattr(staff, "username", "") or str(staff or "")
    target_type = target.__class__.__name__ if target is not None else ""
    target_id = getattr(target, "id", None)
    return AuditLog.objects.create(
        staff_id=staff_id,
        staff_label=staff_label,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail or {},
        ip=ip,
    )
