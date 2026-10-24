"""Print the configured Cloudflare token (panel, else .env) — for scripts/domain.sh dns01 only,
which writes it to the root-only certbot credentials file. Never run it where output is logged."""
from django.core.management.base import BaseCommand, CommandError

from apps.ops.cloudflare import configured_token


class Command(BaseCommand):
    help = "print the Cloudflare API token (for the host's DNS-01 credentials file)"

    def handle(self, *args, **opts):
        token, _source = configured_token()
        if not token:
            raise CommandError("no Cloudflare token")
        self.stdout.write(token)
