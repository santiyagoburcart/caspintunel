from django.apps import AppConfig


class TicketsConfig(AppConfig):
    """Support tickets (site + bot), staff inbox, topic scopes (docs/architecture.md)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tickets"
    label = "tickets"
    verbose_name = "Tickets"
