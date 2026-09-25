"""
Send a test email through whatever mail path is currently configured.

    docker compose exec web python manage.py send_test_email you@example.com

Uses the same path as every app email (apps.common.mail): admin-panel relay →
.env EMAIL_* → local mailserver.
"""
from django.conf import settings
from django.core.mail import get_connection, send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send a test email to verify the mail configuration."

    def add_arguments(self, parser):
        parser.add_argument("to", help="destination address")

    def handle(self, *args, **opts):
        from apps.common.mail import describe_smtp_error, resolve_mail_config

        to = opts["to"]
        cfg = resolve_mail_config()
        self.stdout.write(
            f"source    : {cfg.source}  (admin-panel relay → .env EMAIL_* → local mailserver)\n"
            f"host:port : {cfg.host or '(not set)'}:{cfg.port}  (STARTTLS={cfg.use_tls} SSL={cfg.use_ssl})\n"
            f"from      : {cfg.from_email or settings.DEFAULT_FROM_EMAIL}\n"
            f"to        : {to}\n"
        )
        if not cfg.configured:
            raise CommandError("No SMTP configured — set the relay in the admin panel (Settings → Email).")
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
            d = describe_smtp_error(exc)
            raise CommandError(f"send failed [{d['code']}]: {d['en']} — {d['raw']}") from exc

        if sent:
            self.stdout.write(self.style.SUCCESS("accepted by the SMTP server. Check the inbox."))
        else:
            raise CommandError("send_mail returned 0 — not sent.")
