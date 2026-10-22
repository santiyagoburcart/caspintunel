from django.apps import AppConfig


class CrmConfig(AppConfig):
    """CRM: customer 360, lifecycle stages, inactivity follow-up cases, leads."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.crm"
    label = "crm"
    verbose_name = "CRM"

    def ready(self):
        from . import signals  # noqa: F401 — links "connection problem" tickets to open cases
