from celery import shared_task

from .notify import notify_ticket_task  # noqa: F401 — registers the task with the worker


@shared_task(ignore_result=True)
def auto_close_tickets_task():
    """Beat: close tickets that waited on the customer for `tickets_auto_close_days` — every store (v1.50)."""
    from apps.tenancy.context import for_each_tenant

    from .services import auto_close_stale

    per = for_each_tenant(auto_close_stale, name="auto_close_tickets")
    return {"closed": sum(v for v in per.values() if isinstance(v, int))}
