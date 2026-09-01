"""
Import legacy users from a JSON file.

    python manage.py import_legacy /path/users.json [--overwrite]

File format: a JSON list of objects, each:
    {"username": "...", "email": "...", "name": "...", "phone": "...",
     "telegram_id": 123, "password": "optional-plaintext", "referral_code": "ABC123"}

Users with no `password` are created with an unusable password and must use a
reset path (email / bot / admin) to log in.
"""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.services import import_legacy_users


class Command(BaseCommand):
    help = "Bulk-import legacy users from a JSON file."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--overwrite", action="store_true")

    def handle(self, *args, **opts):
        try:
            with open(opts["path"], encoding="utf-8") as fh:
                rows = json.load(fh)
        except (OSError, ValueError) as exc:
            raise CommandError(f"could not read {opts['path']}: {exc}")

        if not isinstance(rows, list):
            raise CommandError("file must contain a JSON list of user objects")

        summary = import_legacy_users(rows, overwrite=opts["overwrite"])
        self.stdout.write(self.style.SUCCESS(f"done: {summary}"))
