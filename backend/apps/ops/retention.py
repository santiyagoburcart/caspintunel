"""Local backup retention. Backups live in Telegram; the disk keeps only a short
window. Rules (owner, 2026-10-21):

- DB backups (`<project>-*.sql.gz`): delete after `backup_retention_days`
  (setting, default 2) ONLY when Telegram delivery was confirmed
  (`BackupLog.sent_to_telegram`). Unsent ones are re-sent; if that fails they
  stay and the operator is alerted. The newest KEEP_LATEST always stay.
- `pre-update-*.sql.gz` (update.sh): keep the newest PRE_UPDATE_KEEP.
- `migration/*` (migrate-export/import): delete after MIGRATION_DAYS.

Docker rollback images / build cache are host-side: `scripts/docker-cleanup.sh`.
"""
from __future__ import annotations

import logging
import shutil
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.settings_app.utils import get_setting

from .models import BackupLog, BackupStatus, CleanupRun

log = logging.getLogger("caspintunel")

DEFAULT_RETENTION_DAYS = 2
KEEP_LATEST = 2
PRE_UPDATE_KEEP = 3
MIGRATION_DAYS = 7
LOG_ROWS_DAYS = 30          # history rows of already-deleted files
RESEND_PER_RUN = 6          # cap Telegram retries per run (hourly)
ALERT_EVERY = timedelta(hours=6)
RESEND_AFTER = timedelta(minutes=15)
UNSENT_GRACE = timedelta(hours=1)     # an unsent backup older than this is alerted


def backup_dir() -> Path:
    from apps.telegram.backup import BACKUP_DIR

    return Path(BACKUP_DIR)


def retention_days() -> int:
    try:
        days = int(get_setting("backup_retention_days", DEFAULT_RETENTION_DAYS))
    except (TypeError, ValueError):
        days = DEFAULT_RETENTION_DAYS
    return max(1, min(365, days))


def _db_backup_files(root: Path) -> list[Path]:
    files = [p for p in root.glob(f"{settings.PROJECT_NAME}-*.sql.gz") if p.is_file()]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def _size(path: Path) -> int:
    if path.is_dir():
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return path.stat().st_size


def _remove(path: Path) -> int:
    size = _size(path)
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return size


def run_cleanup(*, dry_run: bool = False) -> dict:
    """Apply every retention rule once. Never raises on a single bad file."""
    from apps.telegram.backup import send_backup_file

    root = backup_dir()
    now = timezone.now()
    days = retention_days()
    cutoff = (now - timedelta(days=days)).timestamp()
    freed = 0
    deleted = {"db_backups": 0, "pre_update": 0, "migration": 0, "log_rows": 0, "resent": 0}
    warnings: list[dict] = []

    def drop(path: Path, kind: str) -> bool:
        nonlocal freed
        try:
            freed += _size(path) if dry_run else _remove(path)
        except OSError as exc:
            log.warning("cleanup: could not delete %s: %s", path, exc)
            warnings.append({"file": path.name, "reason": "delete_failed"})
            return False
        deleted[kind] += 1
        return True

    # 1) database backups ------------------------------------------------
    files = _db_backup_files(root) if root.is_dir() else []
    logs = {b.filename: b for b in BackupLog.objects.filter(
        filename__in=[f.name for f in files], status=BackupStatus.OK).order_by("created_at")}
    resends = 0
    overdue = (now - UNSENT_GRACE).timestamp()
    settled = (now - RESEND_AFTER).timestamp()   # never race the backup task's own upload
    for i, path in enumerate(files):
        entry = logs.get(path.name)
        mtime = path.stat().st_mtime
        if (entry is not None and not entry.sent_to_telegram and mtime < settled
                and resends < RESEND_PER_RUN and not dry_run):
            resends += 1
            if send_backup_file(entry, path):
                deleted["resent"] += 1
        sent = entry is not None and entry.sent_to_telegram
        if not sent:
            # kept whatever its age; alert once the hourly retry had its chance
            if mtime < overdue:
                warnings.append({"file": path.name,
                                 "reason": "not_sent" if entry else "no_record",
                                 "error": entry.error[:120] if entry else ""})
            continue
        if i < KEEP_LATEST or mtime >= cutoff:
            continue
        if drop(path, "db_backups") and not dry_run:
            BackupLog.objects.filter(pk=entry.pk).update(local_deleted_at=now)

    # old history rows whose file is gone (deleted here or never on this disk)
    if not dry_run:
        on_disk = {f.name for f in _db_backup_files(root)} if root.is_dir() else set()
        old = BackupLog.objects.filter(created_at__lt=now - timedelta(days=max(LOG_ROWS_DAYS, days)))
        stale = [pk for pk, name in old.values_list("pk", "filename") if name not in on_disk]
        if stale:
            deleted["log_rows"] = BackupLog.objects.filter(pk__in=stale).delete()[0]

    # 2) pre-update dumps (update.sh): newest PRE_UPDATE_KEEP stay -------
    pre = sorted((p for p in root.glob("pre-update-*.sql.gz") if p.is_file()),
                 key=lambda p: p.stat().st_mtime, reverse=True) if root.is_dir() else []
    for path in pre[PRE_UPDATE_KEEP:]:
        drop(path, "pre_update")

    # 3) migration archives ----------------------------------------------
    mig = root / "migration"
    if mig.is_dir():
        mig_cutoff = (now - timedelta(days=MIGRATION_DAYS)).timestamp()
        for path in sorted(mig.iterdir()):
            if path.stat().st_mtime < mig_cutoff:
                drop(path, "migration")

    result = {"dry_run": dry_run, "retention_days": days, "freed_bytes": freed,
              "deleted": deleted, "warnings": warnings}
    if dry_run:
        return result

    run = CleanupRun.objects.create(freed_bytes=freed, deleted=deleted, warnings=warnings)
    if warnings and not CleanupRun.objects.filter(
            alerted=True, ran_at__gte=now - ALERT_EVERY).exists():
        run.alerted = _alert(warnings)
        run.save(update_fields=["alerted"])
    log.info("backup cleanup: freed %s bytes, %s, %s warning(s)", freed, deleted, len(warnings))
    return {**result, "run": run.pk, "alerted": run.alerted}


def _alert(warnings: list[dict]) -> bool:
    """Tell the operator (backup chat) which backups are kept because their
    upload was never confirmed. Best effort — the Monitoring page shows it too."""
    from apps.telegram.config import backup_client, get_bot_config
    from apps.telegram.models import BotType

    cfg = get_bot_config(BotType.BACKUP)
    client = backup_client()
    if not (client and cfg and cfg.backup_chat_id):
        return False
    names = "\n".join(f"• {w['file']} ({w['reason']})" for w in warnings[:15])
    more = f"\n… +{len(warnings) - 15}" if len(warnings) > 15 else ""
    text = (f"⚠️ {len(warnings)} local backup(s) kept: Telegram delivery not confirmed.\n"
            f"{names}{more}\nCheck the backup bot / proxy; they are retried every hour.")
    try:
        client.send_message(cfg.backup_chat_id, text, parse_mode=None)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("cleanup alert failed: %s", exc)
        return False


def storage_snapshot() -> dict:
    """Disk usage + what the backups folder holds + the last cleanup run."""
    root = backup_dir()
    out: dict = {"disk": None, "backups": None, "last_cleanup": None,
                 "retention_days": retention_days()}
    try:
        du = shutil.disk_usage(root if root.exists() else "/")
        out["disk"] = {"total": du.total, "used": du.used, "free": du.free,
                       "percent": round(du.used * 100 / du.total, 1) if du.total else None}
    except OSError:
        pass
    if root.is_dir():
        try:
            files = _db_backup_files(root)
            unsent = set(BackupLog.objects.filter(
                filename__in=[f.name for f in files], sent_to_telegram=False
            ).values_list("filename", flat=True))
            pre = [p for p in root.glob("pre-update-*.sql.gz") if p.is_file()]
            mig = root / "migration"
            out["backups"] = {
                "db_count": len(files), "db_bytes": sum(f.stat().st_size for f in files),
                "unsent_count": len(unsent),
                "pre_update_count": len(pre), "pre_update_bytes": sum(p.stat().st_size for p in pre),
                "migration_bytes": _size(mig) if mig.is_dir() else 0,
            }
        except OSError:
            pass
    last = CleanupRun.objects.order_by("-ran_at").first()
    if last:
        out["last_cleanup"] = {"ran_at": last.ran_at, "freed_bytes": last.freed_bytes,
                               "deleted": last.deleted, "warnings": last.warnings[:20],
                               "warning_count": len(last.warnings)}
    return out
