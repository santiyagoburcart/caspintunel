"""
Telegram Mini App `initData` validation.

A Mini App is our own React user SPA loaded inside Telegram. On launch Telegram
hands the page a signed `initData` string. This module verifies that signature
**server-side** with the sales-bot token — the client-supplied Telegram user id
is never trusted until this passes.

Algorithm (https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app):
  1. parse initData as a query string, url-decoding each value once
  2. pull out `hash`; also drop `signature` (that field is only for Telegram's
     separate Ed25519 third-party check, never part of the bot-token HMAC)
  3. data_check_string = "\n".join(f"{k}={v}") for the remaining keys, sorted
  4. secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)
  5. computed   = hex(HMAC_SHA256(key=secret_key, msg=data_check_string))
  6. constant-time compare computed vs. the received hash
  7. reject if `auth_date` is missing or older than MINIAPP_INITDATA_MAX_AGE
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


class InitDataError(Exception):
    """initData was missing, malformed, expired, or failed the signature check."""


def sales_bot_token() -> str | None:
    """The token of the active/inactive sales bot (decrypted by the field).
    Returns None when no sales bot has been configured yet."""
    from apps.telegram.models import BotType, TelegramConfig

    cfg = TelegramConfig.objects.filter(bot_type=BotType.SALES).first()
    if not cfg or not cfg.token:
        return None
    return cfg.token


def validate_init_data(raw: str, *, bot_token: str, max_age_seconds: int) -> dict:
    """Verify a Mini App initData string. Returns the parsed Telegram user dict
    (and auth_date) on success; raises InitDataError otherwise."""
    if not raw or not isinstance(raw, str):
        raise InitDataError("empty initData")

    fields = dict(parse_qsl(raw, keep_blank_values=True))
    received_hash = fields.pop("hash", "")
    fields.pop("signature", None)  # Ed25519 third-party check only — not in the HMAC
    if not received_hash:
        raise InitDataError("missing hash")

    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        raise InitDataError("signature mismatch")

    try:
        auth_date = int(fields.get("auth_date", "0"))
    except ValueError as exc:
        raise InitDataError("bad auth_date") from exc
    if auth_date <= 0 or (time.time() - auth_date) > max_age_seconds:
        raise InitDataError("initData expired")

    raw_user = fields.get("user", "")
    try:
        user = json.loads(raw_user) if raw_user else None
    except ValueError as exc:
        raise InitDataError("bad user payload") from exc
    if not isinstance(user, dict) or not user.get("id"):
        raise InitDataError("no Telegram user in initData")

    return {"user": user, "auth_date": auth_date}
