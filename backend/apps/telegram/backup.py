"""Database backup → send via the backup bot (build-spec 1.8). Never crashes the app."""
from __future__ import annotations

import gzip
import logging
import os
import shutil
import subprocess
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.ops.models import BackupLog, BackupStatus

from .client import redact_token
from .config import backup_client, get_bot_config
from .models import BotType

log = logging.getLogger("caspintunel")

BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "/app/backups"))
# Bot API (api.telegram.org) refuses uploads above 50 MB; bigger dumps go in parts
TELEGRAM_UPLOAD_LIMIT = 50 * 1000 * 1000
PART_SIZE = 45 * 1024 * 1024


def _dump_database(target: Path) -> int:
    db = settings.DATABASES["default"]
    cmd = [
        "mysqldump",
        "-h", db["HOST"], "-P", str(db["PORT"]), "-u", db["USER"],
        "--single-transaction", "--quick", "--skip-lock-tables",
        # container-to-container on a private docker network; tolerate the
        # server's self-signed cert (MariaDB client) without turning TLS off
        "--skip-ssl-verify-server-cert",
        db["NAME"],
    ]
    # pass the password via env, not argv (argv is visible in `ps`)
    env = {**os.environ, "MYSQL_PWD": db["PASSWORD"]}
    raw = target.with_suffix("")
    with open(raw, "wb") as out:
        subprocess.run(cmd, stdout=out, stderr=subprocess.PIPE, check=True, env=env)
    with open(raw, "rb") as fin, gzip.open(target, "wb") as fout:
        shutil.copyfileobj(fin, fout)
    raw.unlink(missing_ok=True)
    return target.stat().st_size


def run_database_backup() -> BackupLog:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{settings.PROJECT_NAME}-{stamp}.sql.gz"
    path = BACKUP_DIR / filename

    try:
        size = _dump_database(path)
    except (subprocess.CalledProcessError, OSError) as exc:
        detail = getattr(exc, "stderr", b"")
        detail = detail.decode("utf-8", "replace")[:240] if isinstance(detail, bytes) else str(exc)
        log.error("mysqldump failed: %s", detail)
        return BackupLog.objects.create(
            filename=filename, size=0, status=BackupStatus.FAILED, error=detail
        )

    entry = BackupLog.objects.create(filename=filename, size=size, status=BackupStatus.OK)
    send_backup_file(entry, path)
    return entry


def _split(path: Path) -> list[Path]:
    """Cut `path` into PART_SIZE pieces next to it (`<name>.part01` …).
    Restore: `cat <name>.part* > <name>`."""
    parts = []
    with open(path, "rb") as fin:
        i = 0
        while chunk := fin.read(PART_SIZE):
            i += 1
            part = path.with_name(f"{path.name}.part{i:02d}")
            part.write_bytes(chunk)
            parts.append(part)
    return parts


def send_backup_file(entry: BackupLog, path: Path) -> bool:
    """Upload one backup to the backup chat; `sent_to_telegram` is set only
    when Telegram accepted every byte (all parts). Never raises."""
    cfg = get_bot_config(BotType.BACKUP)
    client = backup_client()
    if not (client and cfg and cfg.backup_chat_id):
        log.info("backup bot not configured — kept %s locally only", entry.filename)
        return False

    parts: list[Path] = []
    try:
        if path.stat().st_size <= TELEGRAM_UPLOAD_LIMIT:
            client.send_document(cfg.backup_chat_id, str(path), caption=entry.filename)
        else:
            # over the Bot API upload cap: send it in pieces, never drop it
            parts = _split(path)
            for i, part in enumerate(parts, 1):
                client.send_document(
                    cfg.backup_chat_id, str(part),
                    caption=f"{entry.filename} · part {i}/{len(parts)} · "
                            f"join: cat {entry.filename}.part* > {entry.filename}",
                )
    except Exception as exc:  # noqa: BLE001 - telegram outage must not fail the backup
        entry.error = redact_token(f"send failed: {exc}")[:240]
        entry.save(update_fields=["error"])
        log.warning("backup send to telegram failed: %s", redact_token(exc))
        return False
    finally:
        for part in parts:
            part.unlink(missing_ok=True)

    entry.sent_to_telegram = True
    entry.error = ""
    entry.save(update_fields=["sent_to_telegram", "error"])
    return True
