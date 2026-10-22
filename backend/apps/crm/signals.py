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


def _code_used(sender, instance, **kwargs):
    """A discount code becomes used when the order that reserved it is paid."""
    if instance.status not in ("paid", "completed"):
        return
    from django.utils import timezone

    from .models import DiscountCode

    DiscountCode.objects.filter(order=instance, used_at__isnull=True).update(used_at=timezone.now())


def _connect():
    from django.db.models.signals import post_save as ps

    from apps.orders.models import Order

    ps.connect(_code_used, sender=Order, dispatch_uid="crm_discount_used")


_connect()
