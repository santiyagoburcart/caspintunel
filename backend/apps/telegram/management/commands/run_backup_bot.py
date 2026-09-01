"""
Backup bot process — a tiny, separate bot (own token / chat_id).

The scheduled dump+send is done by the Celery beat task
`apps.telegram.tasks.run_backup_task`; this process only lets an admin:
  /id      → reply with this chat's id (paste into TelegramConfig.backup_chat_id)
  /backup  → trigger a backup now
It idles when no active backup TelegramConfig exists.
"""
import logging
import time

import telebot
from django.core.management.base import BaseCommand

from apps.telegram.config import get_bot_config
from apps.telegram.models import BotType

log = logging.getLogger("caspintunel")


class Command(BaseCommand):
    help = "Run the Telegram backup bot."

    def handle(self, *args, **opts):
        from apps.ops.models import HealthTarget
        from apps.telegram.heartbeat import start_heartbeat

        start_heartbeat(HealthTarget.BOT_BACKUP)

        while True:
            cfg = get_bot_config(BotType.BACKUP)
            if not cfg or not cfg.is_active or not cfg.token:
                self.stdout.write("backup bot: not configured — idling (re-check in 60s)")
                time.sleep(60)
                continue

            if cfg.proxy_url:
                telebot.apihelper.proxy = {"http": cfg.proxy_url, "https": cfg.proxy_url}
            bot = telebot.TeleBot(cfg.token, threaded=False)

            @bot.message_handler(commands=["start", "id"])
            def whoami(msg):
                bot.reply_to(msg, f"chat_id: <code>{msg.chat.id}</code>", parse_mode="HTML")

            @bot.message_handler(commands=["backup"])
            def do_backup(msg):
                from apps.telegram.tasks import run_backup_task

                run_backup_task.delay()
                bot.reply_to(msg, "پشتیبان‌گیری آغاز شد…")

            self.stdout.write("backup bot: polling")
            try:
                bot.infinity_polling(timeout=30, long_polling_timeout=30)
            except Exception as exc:  # noqa: BLE001
                log.error("backup bot: polling error: %s — restarting in 15s", exc)
                time.sleep(15)
