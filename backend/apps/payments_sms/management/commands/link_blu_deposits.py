"""v1.42.2 one-time backfill: link unmatched Blu deposits to payments approved by other routes (manual invoice, staff
receipt approval, SMS, agency) — same tracking / reference number, else exactly one with the same amount and time window
(+ payer name when known). Link only: no approval, nothing counted twice. `--dry-run` shows what would be linked."""
from django.core.management.base import BaseCommand

from apps.payments_sms.blu_link import backfill


class Command(BaseCommand):
    help = "Link unmatched Blu deposits to already approved payments (link only)"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        rows = backfill(dry_run=opts["dry_run"])
        for r in rows:
            self.stdout.write(f"Blu #{r['blu']} → {r.get('payment') or r.get('agency_payment')}")
        self.stdout.write(f"{'would link' if opts['dry_run'] else 'linked'}: {len(rows)}")
