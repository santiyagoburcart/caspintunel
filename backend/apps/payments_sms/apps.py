from django.apps import AppConfig


class PaymentsSmsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.payments_sms"

    def ready(self):
        from . import signals  # noqa: F401 — v1.42.2 Blu auto-link

        signals.connect_agency()
