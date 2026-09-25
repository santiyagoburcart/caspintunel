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


def _bump_public_cache(sender, **kwargs):
    from apps.common.public_cache import bump_public_cache

    bump_public_cache()


# Anything behind /config/, /theme/, /pages/, /plans/ → drop the cached copies.
def _connect_public_cache():
    from django.db.models.signals import post_delete

    from apps.plans.models import Plan

    from .models import Page, SiteConfig, Theme

    for model in (Setting, SiteConfig, Theme, Page, Plan):
        post_save.connect(_bump_public_cache, sender=model, dispatch_uid=f"pubcache-save-{model.__name__}")
        post_delete.connect(_bump_public_cache, sender=model, dispatch_uid=f"pubcache-del-{model.__name__}")


_connect_public_cache()
