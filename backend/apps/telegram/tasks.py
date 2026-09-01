import logging

from celery import shared_task

log = logging.getLogger("caspintunel")


@shared_task
def run_backup_task():
    from .backup import run_database_backup

    entry = run_database_backup()
    return {"backup_log": entry.id, "status": entry.status, "sent": entry.sent_to_telegram}


@shared_task
def sync_required_channels_task():
    """Refresh member counts for the forced-join channels."""
    from .config import sales_client
    from .models import RequiredChannel

    client = sales_client()
    if client is None:
        return {"skipped": "sales bot not configured"}

    from django.utils import timezone

    updated = 0
    for channel in RequiredChannel.objects.filter(is_active=True):
        try:
            count = client._call("getChatMemberCount", chat_id=channel.channel_id)
            channel.member_count = int(count)
            channel.last_synced_at = timezone.now()
            channel.save(update_fields=["member_count", "last_synced_at"])
            updated += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("channel %s member count failed: %s", channel.channel_id, exc)
    return {"updated": updated}
