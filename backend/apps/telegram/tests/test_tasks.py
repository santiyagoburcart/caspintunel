import subprocess

import pytest

from apps.ops.models import BackupStatus
from apps.telegram import backup as backup_mod
from apps.telegram.tasks import run_backup_task, sync_required_channels_task

pytestmark = pytest.mark.django_db


def test_run_backup_task_returns_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_mod, "BACKUP_DIR", tmp_path)

    def _run(cmd, stdout=None, stderr=None, check=None, env=None):
        stdout.write(b"dump\n")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(backup_mod.subprocess, "run", _run)

    result = run_backup_task()
    assert result["status"] == BackupStatus.OK
    assert result["sent"] is False


def test_sync_channels_skips_without_bot():
    assert "skipped" in sync_required_channels_task()
