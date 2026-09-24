import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Setting

log = logging.getLogger("caspintunel")


@receiver(post_save, sender=Setting)
def on_setting_saved(sender, instance: Setting, **kwargs):
    if instance.key == "backup_interval_minutes":
        try:
            from apps.ops.schedule import reconcile_backup_schedule

            reconcile_backup_schedule()
        except Exception as exc:  # noqa: BLE001 - never break a settings save
            log.warning("could not reconcile backup schedule: %s", exc)
    elif instance.key == "service_sync_interval_minutes":
        try:
            from apps.ops.schedule import reconcile_sync_schedule

            reconcile_sync_schedule()
        except Exception as exc:  # noqa: BLE001 - never break a settings save
            log.warning("could not reconcile service sync schedule: %s", exc)
