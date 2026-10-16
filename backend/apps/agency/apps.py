from django.apps import AppConfig


class AgencyConfig(AppConfig):
    """Agency panel (پنل نمایندگی): PAMP v1.5.3's reseller-admin management,
    ported 1:1 (see apps/agency/PORTING.md)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.agency"
    label = "agency"
    verbose_name = "Agency panel"
