"""Agency sync — PAMP v1.5.3 `admins/tasks.py`, ported 1:1 (sha256 c0145a1e…91e4).

Same order of operations: fetch → per admin update → deleted-user tracking
(skipped on a truncated list) → preserved sold volume → remove admins gone
from the panel (never on an empty list) → enforcement → SyncLog.
caspintunel changes (no formula involved): the task is gated by the settings
`agency_sync_enabled` / `agency_enforcement_enabled` (both default OFF), it
does not create `auth.User` rows, and PAMP's Telegram backup task is not
ported. `tests/test_golden.py` proves the results equal the original code's.
"""
import logging
import io
import time
from celery import shared_task
from django.utils import timezone


def sync_enabled() -> bool:
    from apps.settings_app.utils import get_setting
    return bool(get_setting('agency_sync_enabled', False))


def enforcement_enabled() -> bool:
    from apps.settings_app.utils import get_setting
    return bool(get_setting('agency_enforcement_enabled', False))

logger = logging.getLogger('admins')


def track_deleted_users(panel_admin, current_users):
    """
    Compare current users to last snapshot. Accumulate used-traffic of deleted users
    into panel_admin.deleted_users_used_bytes, then refresh the snapshot table.
    Only the sold-volume field (total_user_limit) is affected — called by sync loop.
    """
    from .models import UserTrafficSnapshot

    current_map = {
        u['username']: (u.get('used_traffic') or 0)
        for u in current_users
        if u.get('username')
    }

    prev = {
        s.user_username: s.used_traffic_bytes
        for s in UserTrafficSnapshot.objects.filter(panel_admin=panel_admin)
    }

    deleted = set(prev.keys()) - set(current_map.keys())
    added = sum(prev[u] for u in deleted)

    if added > 0:
        panel_admin.deleted_users_used_bytes = (panel_admin.deleted_users_used_bytes or 0) + added
        panel_admin.save(update_fields=['deleted_users_used_bytes'])
        logger.info(
            "Snapshot: %s — %d deleted user(s), +%d bytes to sold volume",
            panel_admin.username, len(deleted), added,
        )

    if deleted:
        UserTrafficSnapshot.objects.filter(
            panel_admin=panel_admin, user_username__in=deleted
        ).delete()

    # Upsert snapshots for all currently live users
    for uname, used in current_map.items():
        UserTrafficSnapshot.objects.update_or_create(
            panel_admin=panel_admin,
            user_username=uname,
            defaults={'used_traffic_bytes': used},
        )


@shared_task(bind=True, max_retries=3, default_retry_delay=60, name='apps.agency.tasks.sync_panel_admins')
def sync_panel_admins(self):
    # caspintunel: OFF until the cut-over from the Finland PAMP is approved —
    # two syncs on one panel would each accumulate and enforce (setting
    # `agency_sync_enabled`, default false). Everything else is PAMP v1.5.3.
    if not sync_enabled():
        logger.info("Agency sync is disabled (setting agency_sync_enabled) — nothing done.")
        return "disabled"
    return _pamp_sync(self)


def _pamp_sync(self):
    from .models import PanelAdmin, SyncLog
    from .panel_api import PanelAPIClient, PanelAPIError

    start = time.time()
    logger.info("Starting panel admin sync...")

    try:
        client = PanelAPIClient()
        admins_data = client.sync_all_admins()
    except PanelAPIError as exc:
        duration = time.time() - start
        SyncLog.objects.create(
            status=SyncLog.STATUS_FAILED,
            admins_synced=0,
            error_message=str(exc),
            duration_seconds=round(duration, 2),
        )
        logger.error("Panel sync failed: %s", exc)
        raise self.retry(exc=exc)

    synced = 0
    errors = []
    now = timezone.now()

    if not admins_data:
        # /api/admins came back empty — could be a real empty panel, but could also be
        # a bad/partial response. Either way, do NOT run the "remove admins no longer on
        # panel" step below on this data: that would read as "every admin was deleted".
        msg = "/api/admins returned no admins — skipped admin-deletion step this run"
        logger.warning("Panel sync: %s", msg)
        errors.append(msg)

    for data in admins_data:
        uname = data.get('username')

        # get_admin_user_stats() failed for this admin (timeout, rate limit, 5xx,
        # network drop, or an invalid response) — do not touch this admin's row at
        # all this run. Keep its old snapshots/values untouched and let the next
        # scheduled sync retry it, instead of writing stale/empty data over it.
        if data.get('user_stats_error'):
            msg = (
                f"{uname}: /api/users failed — {data['user_stats_error']} "
                f"(skipped this run, old values kept, will retry next sync)"
            )
            errors.append(msg)
            logger.warning(msg)
            continue

        try:
            prev = PanelAdmin.objects.filter(username=data['username']).values('has_data_limit', 'admin_limit_bytes').first()
            if prev is not None:
                old_lim = prev['admin_limit_bytes'] if prev['has_data_limit'] else 0
                new_lim = data['admin_limit_bytes'] if data['has_data_limit'] else 0
                if int(old_lim or 0) != int(new_lim or 0):
                    # our own panel changes update the row at once, so a difference here was made
                    # on PasarGuard directly (or by another tool) — keep it in the limit history
                    from . import limit_history
                    limit_history.record(data['username'], old_lim, new_lim, action="external", source="pasarguard",
                                         note="detected by the sync — changed directly on PasarGuard")
            obj, _ = PanelAdmin.objects.update_or_create(
                username=data['username'],
                defaults={
                    'is_sudo': data['is_sudo'],
                    'is_active': data['is_active'],
                    'status': data['status'],
                    'has_data_limit': data['has_data_limit'],
                    'admin_limit_bytes': data['admin_limit_bytes'],
                    'admin_remaining': data['admin_remaining'],
                    'total_user_limit': data['total_user_limit'],
                    'total_user_used': data['total_user_used'],
                    'user_count': data['user_count'],
                    'active_user_count': data['active_user_count'],
                    'on_hold_users': data['on_hold_users'],
                    'limited_users': data['limited_users'],
                    'disabled_users': data['disabled_users'],
                    'expired_users': data['expired_users'],
                    'raw_data': data['raw_data'],
                    'last_synced_at': now,
                    # the last FINITE limit survives "unlimited" (charges + "Add" start from it)
                    **({'last_limit_bytes': data['admin_limit_bytes']}
                       if data['has_data_limit'] and data['admin_limit_bytes'] > 0 else {}),
                },
            )

            # Detect deleted users and accumulate their used-traffic into sold volume.
            # Must reload obj so deleted_users_used_bytes reflects any prior accumulation.
            obj.refresh_from_db(fields=['deleted_users_used_bytes'])
            if data.get('skip_deleted_detection'):
                # User list hit the fetch cap and may be truncated — comparing it to the
                # last snapshot would make the missing tail users look deleted.
                logger.warning(
                    "Skipping deleted-user detection for '%s' — user list was "
                    "truncated this run.", uname,
                )
            else:
                track_deleted_users(obj, data.get('users', []))

            # Re-read after track_deleted_users may have updated deleted_users_used_bytes.
            obj.refresh_from_db(fields=['deleted_users_used_bytes'])
            preserved = obj.deleted_users_used_bytes or 0
            if preserved:
                # Add preserved sold volume on top of fresh Pasargad value (no double-count:
                # total_user_limit was just written from Pasargad, then we add once).
                PanelAdmin.objects.filter(pk=obj.pk).update(
                    total_user_limit=data['total_user_limit'] + preserved
                )

            # (PAMP creates a Django auth user per admin here for its portal login —
            #  not ported: resellers must not become caspintunel customer users)
            synced += 1
        except Exception as e:
            errors.append(f"{data['username']}: {e}")
            logger.warning("Error saving admin %s: %s", data['username'], e)

    # Remove admins that no longer exist on the panel — never on an empty/failed
    # /api/admins response (handled above; admins_data is falsy in that case).
    if admins_data:
        synced_usernames = {data['username'] for data in admins_data if data.get('username')}
        deleted_count = PanelAdmin.objects.exclude(username__in=synced_usernames).delete()[0]
        if deleted_count:
            logger.info("Removed %d admins no longer on panel", deleted_count)

    # Auto-enforce data limits
    try:
        if enforcement_enabled():
            check_and_enforce_limits()
        else:
            logger.info("Agency enforcement is disabled (setting agency_enforcement_enabled) — skipped.")
    except Exception as e:
        logger.error("Limit enforcement error: %s", e)
        errors.append(f"enforcement: {e}")

    duration = time.time() - start
    status = SyncLog.STATUS_SUCCESS if not errors else SyncLog.STATUS_PARTIAL
    SyncLog.objects.create(
        status=status,
        admins_synced=synced,
        error_message='\n'.join(errors),
        duration_seconds=round(duration, 2),
    )

    logger.info("Sync complete: %d admins in %.1fs.", synced, duration)
    return f"Synced {synced} admins."


def check_and_enforce_limits():
    """Block admins who have consumed their Pasargad data_limit; unblock when limit is raised."""
    from .models import PanelAdmin
    from .panel_api import PanelAPIClient

    limited = PanelAdmin.objects.filter(has_data_limit=True, admin_limit_bytes__gt=0)
    count = limited.count()
    if not count:
        logger.info("Enforcement: no limited admins, skipping")
        return

    logger.info("Enforcement: checking %d limited admin(s)", count)
    client = PanelAPIClient()
    client.authenticate()

    for admin in limited:
        used = admin.admin_used_bytes
        limit = admin.admin_limit_bytes
        pct = (used / limit * 100) if limit > 0 else 0

        if used >= limit and not admin.pamp_blocked:
            logger.warning("Enforcement: BLOCKING %s at %.1f%% (%d/%d)", admin.username, pct, used, limit)
            ok, msg = client.disable_admin(admin.username)
            if ok:
                admin.pamp_blocked = True
                admin.pamp_blocked_at = timezone.now()
                admin.save(update_fields=['pamp_blocked', 'pamp_blocked_at'])
            else:
                logger.error("Enforcement: disable_admin %s failed: %s", admin.username, msg)

        elif used < limit and admin.pamp_blocked:
            logger.info("Enforcement: UNBLOCKING %s at %.1f%%", admin.username, pct)
            ok, msg = client.enable_admin(admin.username)
            if ok:
                admin.pamp_blocked = False
                admin.pamp_blocked_at = None
                admin.save(update_fields=['pamp_blocked', 'pamp_blocked_at'])
            else:
                logger.error("Enforcement: enable_admin %s failed: %s", admin.username, msg)

    logger.info("Enforcement: done")
