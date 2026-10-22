"""A ticket opened in the connection-problem topic joins the customer's open
inactivity case (on commit, so the ticket and its first message exist)."""
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.tickets.models import Ticket


@receiver(post_save, sender=Ticket, dispatch_uid="crm_link_connection_ticket")
def _link(sender, instance, created, **kwargs):
    if not created:
        return

    def run():
        from .services import connection_topic_id, link_ticket

        if instance.topic_id == connection_topic_id():
            link_ticket(instance)

    transaction.on_commit(run)
