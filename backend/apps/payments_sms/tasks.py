from celery import shared_task


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def match_blu_transaction_task(self, pk: int):
    """Match one new Blu deposit (queued after the webhook committed)."""
    from .matching import match_blu_transaction

    try:
        tx = match_blu_transaction(pk)
    except Exception as exc:  # noqa: BLE001 — DB hiccup / lock timeout: try again
        raise self.retry(exc=exc)
    return {"id": pk, "status": tx.status if tx else None}


@shared_task
def blu_stale_check_task():
    """No batch from the Blu collector for BLU_STALE_MINUTES → one Telegram + panel alert."""
    from .blu import check_stale

    return check_stale()
