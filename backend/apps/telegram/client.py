"""
Minimal Telegram Bot API client (raw HTTP, proxy-aware).

Kept independent of any bot framework so it is easy to unit-test and so the
backup path has zero framework weight. Each bot has its own token/proxy, and a
Telegram outage here never propagates to the site or panel — callers catch
`TelegramError` and carry on.
"""
from __future__ import annotations

import logging

import requests

log = logging.getLogger("caspintunel")

_MEMBER_OK = {"member", "administrator", "creator", "owner"}


class TelegramError(Exception):
    pass


class TelegramClient:
    def __init__(self, token: str, proxy_url: str | None = None, timeout: int = 20):
        self._base = f"https://api.telegram.org/bot{token}"
        self._timeout = timeout
        self._session = requests.Session()
        if proxy_url:
            self._session.proxies = {"http": proxy_url, "https": proxy_url}

    def _call(self, method: str, *, files=None, **params):
        try:
            resp = self._session.post(
                f"{self._base}/{method}", data=params, files=files, timeout=self._timeout
            )
        except requests.RequestException as exc:
            raise TelegramError(f"{method}: network error: {exc}") from exc
        try:
            body = resp.json()
        except ValueError:
            raise TelegramError(f"{method}: non-JSON response ({resp.status_code})")
        if not body.get("ok"):
            raise TelegramError(f"{method}: {body.get('description', resp.status_code)}")
        return body["result"]

    # -- helpers ------------------------------------------------------
    def get_me(self) -> dict:
        return self._call("getMe")

    def send_message(self, chat_id, text, *, reply_markup=None, parse_mode="HTML",
                     disable_web_page_preview=True):
        params = dict(chat_id=chat_id, text=text, parse_mode=parse_mode,
                      disable_web_page_preview=disable_web_page_preview)
        if reply_markup is not None:
            import json

            params["reply_markup"] = json.dumps(reply_markup)
        return self._call("sendMessage", **params)

    def send_photo(self, chat_id, photo_bytes: bytes, *, caption=None, filename="qr.png"):
        return self._call("sendPhoto", files={"photo": (filename, photo_bytes, "image/png")},
                          chat_id=chat_id, caption=caption or "")

    def send_document(self, chat_id, file_path: str, *, caption=None):
        with open(file_path, "rb") as fh:
            return self._call("sendDocument", files={"document": fh},
                              chat_id=chat_id, caption=caption or "")

    def get_chat_member(self, chat_id, user_id) -> dict:
        return self._call("getChatMember", chat_id=chat_id, user_id=user_id)

    def is_member(self, chat_id, user_id) -> bool:
        try:
            status = self.get_chat_member(chat_id, user_id).get("status")
        except TelegramError as exc:
            log.warning("getChatMember(%s, %s) failed: %s", chat_id, user_id, exc)
            return False
        return status in _MEMBER_OK
