"""
Telegram Mini App `initData` validation.

A Mini App is our own React user SPA loaded inside Telegram. On launch Telegram
hands the page a signed `initData` string. This module verifies that signature
**server-side** with the sales-bot token — the client-supplied Telegram user id
is never trusted until this passes.

Algorithm (https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app):
  1. parse initData as a query string, url-decoding each value once
  2. pull out `hash`
  3. data_check_string = "\n".join(f"{k}={v}") for the remaining keys, sorted
  4. secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)
  5. computed   = hex(HMAC_SHA256(key=secret_key, msg=data_check_string))
  6. constant-time compare computed vs. the received hash
  7. reject if `auth_date` is missing or older than MINIAPP_INITDATA_MAX_AGE

Telegram Bot API 8.0 added a `signature` field for a *separate* Ed25519
third-party check. Whether it belongs in the bot-token data-check-string has
flip-flopped across clients, so we accept a match computed **either** with or
without it — both still require a valid HMAC of the real bot token.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl

log = logging.getLogger("caspintunel")


class InitDataError(Exception):
    """initData was missing, malformed, expired, or failed the signature check."""


def sales_bot_token() -> str | None:
    """The token of the active/inactive sales bot (decrypted by the field).
    Returns None when no sales bot has been configured yet."""
    from apps.telegram.models import BotType, TelegramConfig

    cfg = TelegramConfig.objects.filter(bot_type=BotType.SALES).first()
    if not cfg or not cfg.token:
        return None
    return (cfg.token or "").strip()


def _hmac_hex(secret_key: bytes, msg: str) -> str:
    return hmac.new(secret_key, msg.encode(), hashlib.sha256).hexdigest()


def validate_init_data(raw: str, *, bot_token: str, max_age_seconds: int,
                       debug: bool = False) -> dict:
    """Verify a Mini App initData string. Returns the parsed Telegram user dict
    (and auth_date) on success; raises InitDataError otherwise."""
    if not raw or not isinstance(raw, str):
        raise InitDataError("empty initData")

    fields = dict(parse_qsl(raw, keep_blank_values=True))
    received_hash = fields.pop("hash", "")
    if not received_hash:
        raise InitDataError("missing hash")

    secret_key = hmac.new(b"WebAppData", (bot_token or "").encode(), hashlib.sha256).digest()

    # candidate A: exclude `signature` (Bot API 8.0 spec)   B: keep it (older clients)
    without_sig = {k: v for k, v in fields.items() if k != "signature"}
    dcs_a = "\n".join(f"{k}={without_sig[k]}" for k in sorted(without_sig))
    dcs_b = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    matched = any(
        hmac.compare_digest(_hmac_hex(secret_key, dcs), received_hash)
        for dcs in ({dcs_a, dcs_b})
    )
    if not matched:
        if debug:
            log.warning(
                "miniapp initData signature mismatch: keys=%s token_len=%d "
                "got=%s… calc_a=%s… calc_b=%s…",
                sorted(fields), len(bot_token or ""), received_hash[:12],
                _hmac_hex(secret_key, dcs_a)[:12], _hmac_hex(secret_key, dcs_b)[:12],
            )
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
