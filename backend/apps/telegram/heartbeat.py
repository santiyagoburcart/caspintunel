"""Background thread that keeps a bot's health heartbeat fresh in Redis."""
from __future__ import annotations

import threading
import time


def start_heartbeat(target: str, interval: int = 30) -> threading.Thread:
    from apps.ops.health import bot_heartbeat

    def _loop():
        while True:
            try:
                bot_heartbeat(target)
            except Exception:  # noqa: BLE001 - cache blip must not kill the bot
                pass
            time.sleep(interval)

    thread = threading.Thread(target=_loop, name=f"heartbeat-{target}", daemon=True)
    thread.start()
    return thread
