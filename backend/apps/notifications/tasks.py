import logging

from celery import shared_task

log = logging.getLogger("caspintunel")


@shared_task
def deliver_notification_task(notification_id: int):
    from .dispatch import broadcast, notify_user
    from .models import Notification

    note = Notification.objects.filter(pk=notification_id).first()
    if not note:
        return {"skipped": "not found"}

    if note.target_user_id:
        notify_user(
            note.target_user, title=note.title, body=note.body, ntype=note.type,
            via_site=note.via_site, via_bot=note.via_bot, via_email=note.via_email,
            notification=note,
        )
        return {"notification": note.id, "recipients": 1}
    return broadcast(note)
