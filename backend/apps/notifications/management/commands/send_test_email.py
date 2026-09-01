"""
Send a test email through whatever mail path is currently configured.

    docker compose exec web python manage.py send_test_email you@example.com

Use it after setting SMTP_RELAY_* (and restarting the mailserver) to confirm
that mail actually leaves the box and reaches an external inbox.
"""
from django.conf import settings
from django.core.mail import get_connection, send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send a test email to verify the mail configuration."

    def add_arguments(self, parser):
        parser.add_argument("to", help="destination address")

    def handle(self, *args, **opts):
        to = opts["to"]
        host = settings.EMAIL_HOST or "(not set)"
        self.stdout.write(
            f"backend  : {settings.EMAIL_BACKEND}\n"
            f"host:port : {host}:{settings.EMAIL_PORT}  (TLS={settings.EMAIL_USE_TLS})\n"
            f"from      : {settings.DEFAULT_FROM_EMAIL}\n"
            f"to        : {to}\n"
        )
        if not settings.EMAIL_HOST and "smtp" in settings.EMAIL_BACKEND:
            raise CommandError(
                "EMAIL_HOST is empty — mail is disabled. Set EMAIL_HOST (and, for "
                "external delivery, SMTP_RELAY_* on the mailserver)."
            )
        try:
            sent = send_mail(
                subject=f"{settings.PROJECT_NAME} — test email",
                message=(
                    "This is a test message from your caspintunel deployment.\n"
                    "If you received it, verification / reset / notification "
                    "emails will reach real users.\n"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[to],
                connection=get_connection(fail_silently=False),
                fail_silently=False,
            )
        except Exception as exc:  # noqa: BLE001 - surface the real error to the operator
            raise CommandError(f"send failed: {exc!r}") from exc

        if sent:
            self.stdout.write(self.style.SUCCESS(
                "handed to the mail server. Check the inbox; if it never arrives, "
                "check `docker compose logs mailserver` for a relay/auth error."
            ))
        else:
            raise CommandError("send_mail returned 0 — not sent.")
