from django.apps import AppConfig


class SettingsAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.settings_app"

    def ready(self):
        from . import signals  # noqa: F401
