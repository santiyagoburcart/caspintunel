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


@shared_task(ignore_result=True)
def store_bot_apply_task(tenant_id: int):
    """v1.49 (Phase 6): webhook + menu button + description of a store's bot again (branding saved)."""
    from .bots import apply
    from .models import TenantBot

    b = TenantBot.objects.filter(tenant_id=tenant_id).first()
    return apply(b).state if b is not None else None


@shared_task(ignore_result=True)
def build_export_task(export_id: int):
    """v1.53 (Phase 10, tenancy/export.py): build one store export — queued inside the store, so it runs there."""
    from .export import build

    return build(export_id)


@shared_task(ignore_result=True)
def store_exports_cleanup_task():
    """v1.53: hourly — delete exports 24 h after they were ready, fail stuck jobs (every store)."""
    from .export import cleanup

    return cleanup()


@shared_task(ignore_result=True)
def store_fees_task():
    """v1.53 (Phase 12, tenancy/fees.py): hourly — monthly fee invoices, reminders, optional suspension / resume.
    Does nothing while no store has its fee switched on (the default)."""
    from .fees import run

    return run()


@shared_task(ignore_result=True)
def scan_import_task(import_id: int):
    """v1.56 (tenancy/importers): read an uploaded dump + one read-only PasarGuard listing → the preview. Queued inside the
    store, so it runs there."""
    from .importers.engine import scan

    return scan(import_id)


@shared_task(ignore_result=True)
def run_import_task(import_id: int):
    """v1.56: the import itself (DB backup first), inside the store."""
    from .importers.engine import run

    return run(import_id)


@shared_task(ignore_result=True)
def store_imports_cleanup_task():
    """v1.56: hourly — delete uploaded dumps 24 h after upload, fail stuck imports (every store)."""
    from .importers.engine import cleanup

    return cleanup()
