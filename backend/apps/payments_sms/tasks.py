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
def blu_service_check_task():
    """Read-only SSH check of the collector service on the Iran server (blu_service.py)."""
    from .blu_service import check_service

    return check_service()


@shared_task
def blu_stale_check_task():
    """No batch from the Blu collector for BLU_STALE_MINUTES → one Telegram + panel alert."""
    from .blu import check_stale

    return check_stale()


@shared_task(bind=True, max_retries=2, default_retry_delay=20)
def rounded_retry_task(self, order_id: int):
    """A receipt was uploaded: a deposit linked to this order as slightly LESS may now be
    approved by the rounded-amount rule (rounded.py)."""
    from .rounded import retry_for_order

    try:
        return retry_for_order(order_id)
    except Exception as exc:  # noqa: BLE001 — lock timeout: try again
        raise self.retry(exc=exc)
