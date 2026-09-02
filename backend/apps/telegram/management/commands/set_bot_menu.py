"""
Point the sales bot's menu button at the Telegram Mini App (our user SPA).

    docker compose exec web python manage.py set_bot_menu
    docker compose exec web python manage.py set_bot_menu --url https://aicaspin.ir/ --text "کاسپین"

Runs automatically every time the sales bot (re)starts; this command is just a
manual trigger / check.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.telegram.client import TelegramError
from apps.telegram.config import sales_client


class Command(BaseCommand):
    help = "Set the sales bot's menu button to open the Mini App."

    def add_arguments(self, parser):
        parser.add_argument("--url", default=getattr(settings, "MINIAPP_URL", ""))
        parser.add_argument("--text", default="🌐 اپ")

    def handle(self, *args, **opts):
        url = opts["url"]
        if not url.startswith("https://"):
            raise CommandError(f"MINIAPP_URL must be https:// (got {url!r})")
        client = sales_client()
        if client is None:
            raise CommandError("sales bot has no active token — set it in the admin panel first")
        try:
            client.set_chat_menu_button(text=opts["text"], url=url)
        except TelegramError as exc:
            raise CommandError(f"Telegram rejected the call: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"menu button -> {url}"))
