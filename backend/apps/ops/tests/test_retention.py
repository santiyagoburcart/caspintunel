"""Local backup retention: only Telegram-confirmed backups are ever deleted."""
import os
import time
from datetime import timedelta

import pytest
import responses
from django.conf import settings
from django.utils import timezone

from apps.ops import retention
from apps.ops.models import BackupLog, BackupStatus, CleanupRun
from apps.settings_app.utils import set_setting
from apps.telegram import backup as backup_mod
from apps.telegram.client import redact_token
from apps.telegram.models import BotType, TelegramConfig

pytestmark = pytest.mark.django_db

API = "https://api.telegram.org/botBTOK"
DAY = 86400


@pytest.fixture
def bdir(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_mod, "BACKUP_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def bot():
    return TelegramConfig.objects.create(bot_type=BotType.BACKUP, token="BTOK", is_active=True,
                                         backup_chat_id=42)


def _age(path, seconds):
    t = time.time() - seconds
    os.utime(path, (t, t))


def make_backup(root, age_s, *, sent=True, record=True, size=100, error=""):
    stamp = timezone.now() - timedelta(seconds=age_s)
    name = f"{settings.PROJECT_NAME}-{stamp:%Y%m%d-%H%M%S}-{age_s}.sql.gz"
    path = root / name
    path.write_bytes(b"x" * size)
    _age(path, age_s)
    if record:
        BackupLog.objects.create(filename=name, size=size, status=BackupStatus.OK,
                                 sent_to_telegram=sent, error=error)
    return path


def test_deletes_only_confirmed_backups_past_retention(bdir):
    keep_new = [make_backup(bdir, s) for s in (60, 3600, DAY)]
    old_sent = make_backup(bdir, 3 * DAY)
    old_unsent = make_backup(bdir, 4 * DAY, sent=False, error="send failed: timeout")
    no_record = make_backup(bdir, 5 * DAY, record=False)

    out = retention.run_cleanup()

    assert all(p.exists() for p in keep_new)
    assert not old_sent.exists()
    assert old_unsent.exists() and no_record.exists()
    assert out["deleted"]["db_backups"] == 1
    assert out["freed_bytes"] == 100
    assert {w["file"]: w["reason"] for w in out["warnings"]} == {
        old_unsent.name: "not_sent", no_record.name: "no_record"}
    assert BackupLog.objects.get(filename=old_sent.name).local_deleted_at is not None
    run = CleanupRun.objects.get()
    assert run.freed_bytes == 100 and len(run.warnings) == 2


def test_latest_two_always_stay_even_if_old(bdir):
    files = [make_backup(bdir, s * DAY) for s in (10, 11, 12)]
    retention.run_cleanup()
    assert files[0].exists() and files[1].exists()
    assert not files[2].exists()


def test_retention_days_setting(bdir):
    set_setting("backup_retention_days", 5, "int")
    files = [make_backup(bdir, s) for s in (60, 120, 3 * DAY, 6 * DAY)]
    retention.run_cleanup()
    assert [p.exists() for p in files] == [True, True, True, False]


@responses.activate
def test_unsent_backup_is_resent_then_deleted(bdir, bot):
    responses.add(responses.POST, f"{API}/sendDocument", json={"ok": True, "result": {}})
    for s in (60, 120):
        make_backup(bdir, s)
    old = make_backup(bdir, 3 * DAY, sent=False, error="send failed: x")

    out = retention.run_cleanup()

    entry = BackupLog.objects.get(filename=old.name)
    assert entry.sent_to_telegram is True and entry.error == ""
    assert not old.exists()
    assert out["deleted"]["resent"] == 1
    assert out["warnings"] == []


@responses.activate
def test_failed_resend_keeps_file_and_alerts_once(bdir, bot):
    responses.add(responses.POST, f"{API}/sendDocument", json={"ok": False, "description": "down"},
                  status=502)
    responses.add(responses.POST, f"{API}/sendMessage", json={"ok": True, "result": {}})
    for s in (60, 120):
        make_backup(bdir, s)
    old = make_backup(bdir, 3 * DAY, sent=False)

    first = retention.run_cleanup()
    second = retention.run_cleanup()

    assert old.exists()
    assert first["alerted"] is True
    assert second["alerted"] is False          # throttled (6 h)
    alerts = [c for c in responses.calls if c.request.url.endswith("/sendMessage")]
    assert len(alerts) == 1
    assert old.name in alerts[0].request.body


def test_recent_unsent_backup_is_not_alerted(bdir):
    make_backup(bdir, 600, sent=False)
    assert retention.run_cleanup()["warnings"] == []


def test_pre_update_dumps_keep_newest_three(bdir):
    dumps = []
    for i in range(5):
        p = bdir / f"pre-update-1.15.{i}-x.sql.gz"
        p.write_bytes(b"d" * 10)
        _age(p, (5 - i) * DAY)          # .4 newest
        dumps.append(p)
    out = retention.run_cleanup()
    assert [p.exists() for p in dumps] == [False, False, True, True, True]
    assert out["deleted"]["pre_update"] == 2


def test_migration_archives_deleted_after_seven_days(bdir):
    mig = bdir / "migration"
    mig.mkdir()
    old_dir = mig / "before-import-1"
    old_dir.mkdir()
    (old_dir / "db.sql.gz").write_bytes(b"z" * 50)
    _age(old_dir, 8 * DAY)
    old_tar = mig / "caspintunel-migration-1.tar.enc"
    old_tar.write_bytes(b"t" * 30)
    _age(old_tar, 8 * DAY)
    new_tar = mig / "caspintunel-migration-2.tar.enc"
    new_tar.write_bytes(b"t")

    out = retention.run_cleanup()

    assert not old_dir.exists() and not old_tar.exists() and new_tar.exists()
    assert out["deleted"]["migration"] == 2
    assert out["freed_bytes"] == 80


def test_dry_run_deletes_nothing(bdir):
    for s in (60, 120):
        make_backup(bdir, s)
    old = make_backup(bdir, 3 * DAY)
    out = retention.run_cleanup(dry_run=True)
    assert old.exists()
    assert out["deleted"]["db_backups"] == 1
    assert not CleanupRun.objects.exists()


def test_old_history_rows_without_file_are_trimmed(bdir):
    gone = BackupLog.objects.create(filename="gone.sql.gz", status=BackupStatus.OK, sent_to_telegram=True)
    BackupLog.objects.filter(pk=gone.pk).update(created_at=timezone.now() - timedelta(days=40))
    recent = BackupLog.objects.create(filename="recent.sql.gz", status=BackupStatus.OK)
    retention.run_cleanup()
    assert not BackupLog.objects.filter(pk=gone.pk).exists()
    assert BackupLog.objects.filter(pk=recent.pk).exists()


@responses.activate
def test_big_backup_is_sent_in_parts(bdir, bot, monkeypatch):
    monkeypatch.setattr(backup_mod, "TELEGRAM_UPLOAD_LIMIT", 100)
    monkeypatch.setattr(backup_mod, "PART_SIZE", 40)
    responses.add(responses.POST, f"{API}/sendDocument", json={"ok": True, "result": {}})
    path = make_backup(bdir, 60, sent=False, size=250)
    entry = BackupLog.objects.get(filename=path.name)

    assert backup_mod.send_backup_file(entry, path) is True
    assert len(responses.calls) == 7                       # ceil(250 / 40)
    assert b"part 7/7" in responses.calls[-1].request.body
    assert sorted(p.name for p in bdir.iterdir()) == [path.name]   # parts cleaned up
    entry.refresh_from_db()
    assert entry.sent_to_telegram is True


@responses.activate
def test_failed_part_means_not_sent(bdir, bot, monkeypatch):
    monkeypatch.setattr(backup_mod, "TELEGRAM_UPLOAD_LIMIT", 100)
    monkeypatch.setattr(backup_mod, "PART_SIZE", 60)
    responses.add(responses.POST, f"{API}/sendDocument", json={"ok": True, "result": {}})
    responses.add(responses.POST, f"{API}/sendDocument", json={"ok": False, "description": "too big"},
                  status=413)
    path = make_backup(bdir, 60, sent=False, size=150)
    entry = BackupLog.objects.get(filename=path.name)

    assert backup_mod.send_backup_file(entry, path) is False
    entry.refresh_from_db()
    assert entry.sent_to_telegram is False and "too big" in entry.error
    assert sorted(p.name for p in bdir.iterdir()) == [path.name]


def test_token_is_redacted_from_errors():
    msg = "Max retries exceeded with url: /bot123456789:AAFakeTok_-x/sendDocument (Caused by …)"
    assert redact_token(msg) == "Max retries exceeded with url: /bot<token>/sendDocument (Caused by …)"


def test_storage_snapshot(bdir):
    make_backup(bdir, 60)
    make_backup(bdir, 120, sent=False)
    (bdir / "pre-update-1-x.sql.gz").write_bytes(b"p" * 7)
    retention.run_cleanup()
    snap = retention.storage_snapshot()
    assert snap["disk"]["total"] > 0
    assert snap["backups"]["db_count"] == 2 and snap["backups"]["unsent_count"] == 1
    assert snap["backups"]["pre_update_count"] == 1 and snap["backups"]["pre_update_bytes"] == 7
    assert snap["retention_days"] == 2
    assert snap["last_cleanup"]["freed_bytes"] == 0
