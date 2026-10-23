from celery import shared_task


@shared_task
def domain_tick_task():
    """Domain wizard (docs/domain.md): fold in the host's results; remove the
    old domain once its transition period is over."""
    from . import domain

    domain.tick()
