from celery import shared_task


@shared_task(ignore_result=True)
def crm_detect_task():
    """Hourly: inactivity cases, auto-close on reconnect, optional friendly message, stages."""
    from .services import detect_inactivity, refresh_all_stages

    out = detect_inactivity()
    out["stages_changed"] = refresh_all_stages()
    return out
