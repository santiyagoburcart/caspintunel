from celery import shared_task


@shared_task
def domain_tick_task():
    """Domain wizard (docs/domain.md): fold in the host's results; remove the
    old domain once its transition period is over."""
    from . import domain

    domain.tick()


@shared_task(ignore_result=True)
def access_switch_task(sid: str):
    """Settings → Domain & Cloudflare → Access mode: one switch (DNS + verification + auto-revert)."""
    from .access import run_switch

    run_switch(sid)


@shared_task(ignore_result=True)
def access_tick_task():
    """Every 5 min: fold in the host's nginx result; daily: refresh Cloudflare's IP ranges."""
    from django.core.cache import cache

    from .access import refresh_cf_ranges, sync_host

    sync_host()
    if cache.add("access:cf-ranges-refreshed", 1, 24 * 3600):
        refresh_cf_ranges()
