"""manage.py import_pamp_dump FILE [--replace] [--dry-run]

Copies a PAMP MySQL dump (plain .sql or .sql.gz) 1:1 into the agency tables
and verifies every value. Refuses while the agency sync is enabled (the
imported state would be overwritten by the next run).
"""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.agency.pamp_import import DumpError, import_dump
from apps.agency.tasks import sync_enabled


class Command(BaseCommand):
    help = "Import a PAMP MySQL dump into the agency tables (1:1, verified)."

    def add_arguments(self, parser):
        parser.add_argument("file")
        parser.add_argument("--replace", action="store_true", help="overwrite existing agency data")
        parser.add_argument("--dry-run", action="store_true", help="parse and report only")
        parser.add_argument("--force", action="store_true", help="import although agency sync is enabled")

    def handle(self, *args, file, replace, dry_run, force, **opts):
        if sync_enabled() and not dry_run and not force:
            raise CommandError("agency sync is enabled — turn it off first (or --force)")
        try:
            report = import_dump(file, replace=replace, dry_run=dry_run)
        except (DumpError, OSError) as exc:
            raise CommandError(str(exc)) from exc
        for w in report["warnings"]:
            self.stderr.write(self.style.WARNING(f"!! {w}"))
        self.stdout.write(json.dumps(report, indent=1, default=str))
        if not dry_run:
            self.stdout.write(self.style.SUCCESS("imported and verified 1:1"))
