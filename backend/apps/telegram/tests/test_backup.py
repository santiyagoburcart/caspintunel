import subprocess

import pytest
import responses

from apps.ops.models import BackupLog, BackupStatus
from apps.telegram import backup as backup_mod
from apps.telegram.models import BotType, TelegramConfig

pytestmark = pytest.mark.django_db

API = "https://api.telegram.org/botBTOK"


@pytest.fixture
def backup_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_mod, "BACKUP_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def fake_dump(monkeypatch):
    def _run(cmd, stdout=None, stderr=None, check=None, env=None):
        stdout.write(b"-- caspintunel dump --\n" * 50)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(backup_mod.subprocess, "run", _run)


@responses.activate
def test_backup_ok_and_sent(backup_dir, fake_dump):
    TelegramConfig.objects.create(bot_type=BotType.BACKUP, token="BTOK", is_active=True,
                                  backup_chat_id=42)
    responses.add(responses.POST, f"{API}/sendDocument", json={"ok": True, "result": {"message_id": 1}})

    entry = backup_mod.run_database_backup()
    assert entry.status == BackupStatus.OK
    assert entry.size > 0
    assert entry.sent_to_telegram is True
    assert (backup_dir / entry.filename).exists()


def test_backup_ok_but_no_bot_configured(backup_dir, fake_dump):
    entry = backup_mod.run_database_backup()
    assert entry.status == BackupStatus.OK
    assert entry.sent_to_telegram is False


def test_backup_dump_failure_is_logged_not_raised(backup_dir, monkeypatch):
    def _boom(cmd, stdout=None, stderr=None, check=None, env=None):
        raise subprocess.CalledProcessError(1, cmd, stderr=b"access denied")

    monkeypatch.setattr(backup_mod.subprocess, "run", _boom)
    entry = backup_mod.run_database_backup()
    assert entry.status == BackupStatus.FAILED
    assert "access denied" in entry.error
    assert BackupLog.objects.filter(status=BackupStatus.FAILED).count() == 1


@responses.activate
def test_backup_send_failure_does_not_fail_backup(backup_dir, fake_dump):
    TelegramConfig.objects.create(bot_type=BotType.BACKUP, token="BTOK", is_active=True,
                                  backup_chat_id=42)
    responses.add(responses.POST, f"{API}/sendDocument",
                  json={"ok": False, "description": "flood"}, status=429)
    entry = backup_mod.run_database_backup()
    assert entry.status == BackupStatus.OK
    assert entry.sent_to_telegram is False
    assert "send failed" in entry.error
