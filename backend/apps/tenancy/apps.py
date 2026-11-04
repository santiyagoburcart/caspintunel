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
