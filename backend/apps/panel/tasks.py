import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.common.models import write_audit

from .exceptions import PanelError, PanelUnavailable
from .models import Service, ServiceStatus
from .services import (
    apply_scheduled_renewal,
    get_active_panel,
    provision_service,
    renew_service,
    sync_service,
)

log = logging.getLogger("caspintunel")

# statuses worth polling regularly
_SYNCABLE = (
    ServiceStatus.ACTIVE,
    ServiceStatus.ON_HOLD,
    ServiceStatus.LIMITED,
    ServiceStatus.PENDING,
)

_RETRY = dict(
    autoretry_for=(PanelUnavailable,),
    retry_backoff=10,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=6,
)


@shared_task(bind=True, **_RETRY)
def provision_service_task(self, service_id: int, plan_id: int | None = None):
    plan = None
    if plan_id:
        from apps.plans.models import Plan

        plan = Plan.objects.filter(pk=plan_id).first()
    try:
        provision_service(service_id, plan=plan)
    except PanelUnavailable:
        raise
    except PanelError as exc:
        log.error("provision_service_task(%s) failed permanently: %s", service_id, exc)
        _flag_provision_failure(service_id, str(exc))
        raise


@shared_task(bind=True, **_RETRY)
def renew_service_task(self, service_id: int, plan_id: int):
    from apps.plans.models import Plan

    plan = Plan.objects.get(pk=plan_id)
    try:
        renew_service(service_id, plan)
    except PanelUnavailable:
        raise
    except PanelError as exc:
        log.error("renew_service_task(%s) failed: %s", service_id, exc)
        raise


@shared_task(bind=True, **_RETRY)
def sync_service_task(self, service_id: int):
    sync_service(service_id)


@shared_task
def sync_all_services():
    """Celery-beat: refresh usage / expiry / online for every live service."""
    if not settings.PANEL_SYNC_ENABLED:
        return {"skipped": "PANEL_SYNC_ENABLED is false"}
    if get_active_panel() is None:
        return {"skipped": "no active panel"}

    ids = list(
        Service.objects.filter(status__in=_SYNCABLE)
        .exclude(panel_username="")
        .values_list("id", flat=True)
    )
    for sid in ids:
        sync_service_task.delay(sid)
    return {"dispatched": len(ids), "at": timezone.now().isoformat()}


@shared_task(bind=True, **_RETRY)
def apply_scheduled_renewal_task(self, scheduled_renewal_id: int):
    try:
        apply_scheduled_renewal(scheduled_renewal_id)
    except PanelUnavailable:
        raise
    except PanelError as exc:
        log.error("apply_scheduled_renewal_task(%s) failed: %s", scheduled_renewal_id, exc)
        raise


@shared_task
def apply_due_scheduled_renewals():
    """Celery-beat, every 5 minutes: apply any paid renewal whose service has
    already reached the end of its cycle — either time-expired or out of
    volume (ServiceStatus.LIMITED) — while sitting on an unapplied
    ScheduledRenewal."""
    from apps.orders.models import ScheduledRenewal

    due_ids = list(
        ScheduledRenewal.objects.filter(
            applied_at__isnull=True,
            service__status__in=(ServiceStatus.EXPIRED, ServiceStatus.LIMITED),
        ).values_list("id", flat=True)
    )
    for rid in due_ids:
        apply_scheduled_renewal_task.delay(rid)
    return {"dispatched": len(due_ids), "at": timezone.now().isoformat()}


def _flag_provision_failure(service_id: int, detail: str) -> None:
    service = Service.objects.filter(pk=service_id).first()
    if not service:
        return
    write_audit(action="service.provision_failed", target=service, detail={"error": detail})
    log.error("service %s needs admin attention: %s", service_id, detail)
