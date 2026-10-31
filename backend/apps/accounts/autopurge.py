"""Automatic permanent delete of users that sat in the trash too long (v1.32).

Settings (Super Admin, Settings → Auto-purge): `deleted_purge_enabled` (default off) and
`deleted_purge_days` (default 30). A daily beat task calls `purge_user` (accounts/purge.py,
the ONE implementation) for each user soft-deleted more than N days ago, with the
PasarGuard accounts deleted too. Same rules as the button: every panel account is read
first, and a PasarGuard problem purges nothing for that user. That user stays in the trash
and is tried again the next day; staff get one alert per day listing the failures.

Every purge writes its own `user.purged` audit entry (staff "system"); each run also writes one
`users.auto_purged` entry with counts and user ids only (no personal data).
"""
from __future__ import annotations

import logging
import math
from datetime import timedelta

from django.utils import timezone

from apps.common.models import write_audit

from .models import User

log = logging.getLogger("caspintunel")

SYSTEM = "system"
DEFAULT_DAYS = 30
MAX_PER_RUN = 200


def config() -> dict:
    from apps.settings_app.utils import get_setting

    days = int(get_setting("deleted_purge_days", DEFAULT_DAYS) or DEFAULT_DAYS)
    return {"enabled": bool(get_setting("deleted_purge_enabled", False)), "days": max(1, days)}


def due_users(days: int, now=None):
    cutoff = (now or timezone.now()) - timedelta(days=days)
    return (User.objects.filter(deleted_at__isnull=False, deleted_at__lte=cutoff, purged_at__isnull=True)
            .order_by("deleted_at", "id"))


def _task():
    from django_celery_beat.models import PeriodicTask

    from apps.ops.schedule import AUTO_PURGE_TASK

    return PeriodicTask.objects.filter(name=AUTO_PURGE_TASK).select_related("interval").first()


def next_run(now=None):
    """When the daily task runs next (last run + its interval; soon, if it never ran)."""
    now = now or timezone.now()
    task = _task()
    if task is None or not task.enabled:
        return None
    every = timedelta(minutes=task.interval.every if task.interval_id else 1440)
    if task.last_run_at is None:
        return now
    nxt = task.last_run_at + every
    while nxt < now:
        nxt += every
    return nxt


def purge_date(deleted_at, days: int, first_run, every=timedelta(days=1)):
    """The run that will purge a user deleted at `deleted_at`: the first run on or after deleted_at + days."""
    if deleted_at is None or first_run is None:
        return None
    due = deleted_at + timedelta(days=days)
    if due <= first_run:
        return first_run
    return first_run + every * math.ceil((due - first_run) / every)


def status(now=None, *, days: int | None = None) -> dict:
    """What the Deleted users page shows. `days` (Settings, before turning it on): how many users
    such a setting would purge on its first run (`would_purge`)."""
    now = now or timezone.now()
    cfg = config()
    out = {**cfg, "next_run": None, "due_now": 0, "next_purge_at": None, "last_run": None}
    if days is not None:
        out["would_purge"] = due_users(max(1, int(days)), now).count()
    task = _task()
    if task is not None:
        out["last_run"] = task.last_run_at
    if not cfg["enabled"]:
        return out
    nxt = next_run(now)
    out["next_run"] = nxt
    out["due_now"] = due_users(cfg["days"], now).count()
    first = (User.objects.filter(deleted_at__isnull=False, purged_at__isnull=True)
             .order_by("deleted_at").values_list("deleted_at", flat=True).first())
    out["next_purge_at"] = purge_date(first, cfg["days"], nxt) if first else None
    return out


def run(now=None) -> dict:
    """The daily task. Nothing happens while the setting is off."""
    from .purge import PurgeError, purge_user

    cfg = config()
    if not cfg["enabled"]:
        return {"enabled": False}
    purged, failed = [], []
    for user in due_users(cfg["days"], now)[:MAX_PER_RUN]:
        try:
            purge_user(user, staff=SYSTEM, delete_on_panel=True)
            purged.append(user.pk)
        except PurgeError as exc:
            failed.append({"user_id": user.pk, "code": exc.code, "error": str(exc)[:300]})
            log.warning("auto-purge: user %s not purged: %s", user.pk, exc)
        except Exception as exc:  # noqa: BLE001 — one user never stops the run
            failed.append({"user_id": user.pk, "code": "error", "error": f"{type(exc).__name__}: {exc}"[:300]})
            log.exception("auto-purge: user %s failed", user.pk)
    result = {"enabled": True, "days": cfg["days"], "purged": len(purged), "failed": len(failed)}
    if purged or failed:
        # ids + error codes only: the error text can name a PasarGuard account (personal), so it stays out
        write_audit(action="users.auto_purged", staff=SYSTEM, detail={
            "days": cfg["days"], "purged_ids": purged, "failed": [{"user_id": f["user_id"], "code": f["code"]}
                                                                 for f in failed]})
    if failed:
        _alert(failed)
    log.info("auto-purge: %s", result)
    return result


def _alert(failed: list[dict]) -> None:
    from apps.common.staff_alert import alert_staff

    lines = "\n".join(f"• #{f['user_id']}: {f['error'][:160]}" for f in failed[:10])
    alert_staff(f"⚠️ حذف دائمی خودکار: {len(failed)} کاربر حذف نشد (پاسارگارد یا خطا) — فردا دوباره تلاش می‌شود.\n"
                f"Auto-purge: {len(failed)} user(s) not purged — retried tomorrow.\n{lines}",
                perm="users.purge", dedupe_key=f"autopurge:fail:{timezone.now():%Y-%m-%d}", ttl=86400)
