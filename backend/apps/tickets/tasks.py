from celery import shared_task

from .notify import notify_ticket_task  # noqa: F401 — registers the task with the worker


@shared_task(ignore_result=True)
def auto_close_tickets_task():
    """Beat: close tickets that waited on the customer for `tickets_auto_close_days`."""
    from .services import auto_close_stale

    return {"closed": auto_close_stale()}
