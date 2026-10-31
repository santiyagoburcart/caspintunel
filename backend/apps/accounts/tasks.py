from celery import shared_task


@shared_task(name="apps.accounts.tasks.auto_purge_deleted_users_task")
def auto_purge_deleted_users_task():
    from .autopurge import run

    return run()
