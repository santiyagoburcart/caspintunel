from django.apps import AppConfig


class TenancyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tenancy"
    label = "tenancy"
    verbose_name = "Tenants (reseller stores)"

    def ready(self):
        # Phase 1 Release B: scope every tenant table to the current tenant (apps/tenancy/scoping.py)
        from django.apps import apps

        from . import registry, scoping

        scoping.install([apps.get_model(label) for label in registry.TENANT])
        # v1.46 (Phase 4): Celery tasks run for the store they were queued from (apps/tenancy/celery_ctx.py)
        from . import celery_ctx  # noqa: F401
        # v1.49 (Phase 6): a store's branding saved → its bot's description / Mini App button follow (tenancy/bots.py)
        from django.db.models.signals import post_save

        post_save.connect(_branding_saved, sender="settings_app.TenantBranding", dispatch_uid="tenancy_bot_branding")


def _branding_saved(sender, instance, **kwargs):
    from django.db import transaction

    from .models import TenantBot

    if TenantBot.objects.filter(tenant_id=instance.tenant_id).exists():
        from .tasks import store_bot_apply_task

        tid = instance.tenant_id
        transaction.on_commit(lambda: store_bot_apply_task.delay(tid))
