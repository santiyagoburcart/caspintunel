"""Run the local backup retention once (the hourly beat task does the same).

    python manage.py cleanup_backups [--dry-run]
"""
import json

from django.core.management.base import BaseCommand

from apps.ops.retention import run_cleanup, storage_snapshot


class Command(BaseCommand):
    help = "Apply the local backup retention rules once (only Telegram-confirmed backups are deleted)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="only report what would be deleted")

    def handle(self, *args, dry_run=False, **opts):
        result = run_cleanup(dry_run=dry_run)
        disk = storage_snapshot()["disk"]
        self.stdout.write(json.dumps({**result, "disk": disk}, indent=2, default=str))
