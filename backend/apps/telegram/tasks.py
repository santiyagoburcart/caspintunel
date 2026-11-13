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
    """Refresh member counts for the forced-join channels — every store, through its own bot (v1.50)."""
    from apps.tenancy.context import for_each_tenant

    return for_each_tenant(_sync_required_channels, name="sync_required_channels")


def _sync_required_channels():
    from .config import sales_client
    from .models import RequiredChannel

    client = sales_client()
    if client is None:
        return {"skipped": "no bot for this store"}

    from .channels import refresh

    updated = 0
    for channel in RequiredChannel.objects.filter(is_active=True):
        try:
            refresh(channel, client)            # v1.60.1: also whether the bot is still admin there (stores enforce only then)
            updated += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("channel %s member count failed: %s", channel.channel_id, exc)
    return {"updated": updated}


@shared_task(ignore_result=True)
def store_bot_update_task(tenant_id: int, update: dict):
    """v1.49 (Phase 6): one Telegram update for a store's bot (apps/telegram/webhook.py) — the sales bot's handlers,
    inside that store's tenant context."""
    from apps.tenancy.context import tenant_context

    from .bot import store_bots

    with tenant_context(tenant_id):
        return store_bots.process(tenant_id, update)


@shared_task(ignore_result=True)
def store_bots_check_task():
    """v1.49 (Phase 6): every store bot's webhook state (tenancy/bots.py::check_all) — puts a wrong webhook back, alerts us."""
    from apps.tenancy.bots import check_all

    return check_all()
