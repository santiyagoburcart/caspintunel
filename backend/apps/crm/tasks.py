from celery import shared_task


@shared_task(ignore_result=True)
def crm_detect_task():
    """Hourly: inactivity cases, auto-close on reconnect, optional friendly message, stages — for every store (v1.50)."""
    from apps.tenancy.context import for_each_tenant

    from .retention import run_winback
    from .services import detect_inactivity, refresh_all_stages

    def one_store():
        out = detect_inactivity()
        out["winback"] = run_winback()
        out["stages_changed"] = refresh_all_stages()
        return out

    return for_each_tenant(one_store, name="crm_detect")
