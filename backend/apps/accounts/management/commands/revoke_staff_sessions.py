"""End every staff/admin session (access + refresh tokens) without touching
customer logins or SECRET_KEY. Staff simply log in again."""
from django.core.management.base import BaseCommand
from django.db.models import F

from apps.accounts.models import Staff


class Command(BaseCommand):
    help = "Invalidate all staff JWTs (bumps Staff.token_version). Customers stay logged in."

    def add_arguments(self, parser):
        parser.add_argument("--username", help="only this staff account")

    def handle(self, *args, **opts):
        qs = Staff.objects.all()
        if opts.get("username"):
            qs = qs.filter(username=opts["username"])
        n = qs.update(token_version=F("token_version") + 1)
        self.stdout.write(self.style.SUCCESS(f"revoked sessions of {n} staff account(s)"))
