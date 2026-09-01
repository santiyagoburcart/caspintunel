"""
Sales bot process. Runs long-polling when a sales TelegramConfig is active;
otherwise idles (so the container never crash-loops while unconfigured).
Telegram being unreachable here never affects the site or panel.
"""
import logging
import time

from django.core.management.base import BaseCommand

log = logging.getLogger("caspintunel")


class Command(BaseCommand):
    help = "Run the Telegram sales bot (long-polling)."

    def handle(self, *args, **opts):
        from apps.ops.models import HealthTarget
        from apps.telegram.bot.sales_bot import build_bot
        from apps.telegram.heartbeat import start_heartbeat

        start_heartbeat(HealthTarget.BOT_SALES)

        while True:
            try:
                bot = build_bot()
            except Exception as exc:  # noqa: BLE001
                log.error("sales bot: build failed: %s", exc)
                bot = None

            if bot is None:
                self.stdout.write("sales bot: not configured — idling (re-check in 60s)")
                time.sleep(60)
                continue

            self.stdout.write("sales bot: polling")
            try:
                bot.infinity_polling(timeout=30, long_polling_timeout=30)
            except Exception as exc:  # noqa: BLE001 - keep the process alive
                log.error("sales bot: polling error: %s — restarting in 15s", exc)
                time.sleep(15)
