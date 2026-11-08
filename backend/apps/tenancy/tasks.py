from celery import shared_task


@shared_task(ignore_result=True)
def store_domains_tick_task():
    """v1.45 store domains (tenancy/domains.py): DNS checks, certificate / nginx results from the host watcher, health."""
    from .domains import tick

    return tick()


@shared_task(ignore_result=True)
def store_domain_check_task(domain_id: int):
    """«بررسی الان» for one domain (staff action) — the same step as the tick."""
    from .domains import tick

    return tick(only=domain_id)


@shared_task(ignore_result=True)
def store_quota_warnings_task():
    """v1.46 (Phase 4, tenancy/quota.py): 20 % / 10 % reseller quota left → portal notice + staff alert, once per level."""
    from .quota import warn_all

    return warn_all()
