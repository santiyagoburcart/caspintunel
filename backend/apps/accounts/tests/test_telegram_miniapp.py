"""
Telegram Mini App session start — initData is verified server-side against the
sales-bot token before any JWT is issued.
"""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Source, User
from apps.telegram.models import BotType, TelegramConfig

pytestmark = pytest.mark.django_db

BOT_TOKEN = "123456:TEST-sales-bot-token"
URL = "/api/v1/auth/telegram/miniapp/"


@pytest.fixture
def sales_bot():
    return TelegramConfig.objects.create(bot_type=BotType.SALES, token=BOT_TOKEN, is_active=True)


def _sign(fields: dict, token: str = BOT_TOKEN) -> str:
    """Build a correctly-signed initData query string, the way Telegram does."""
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields = dict(fields)
    fields["hash"] = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def _fields(tg_id=777001, username="tg_user", auth_date=None):
    return {
        "auth_date": str(int(auth_date if auth_date is not None else time.time())),
        "query_id": "AAABBBCCC",
        "user": json.dumps({"id": tg_id, "first_name": "Tg", "last_name": "User",
                            "username": username, "language_code": "fa"}),
    }


@pytest.fixture
def client():
    return APIClient()


def test_valid_initdata_with_signature_field(client, sales_bot):
    """Bot API 8.0 clients add a `signature` field; the launch must still validate
    whether or not that field is folded into the bot-token HMAC."""
    f = _fields(tg_id=8001)
    f["chat_instance"] = "-123456789"
    f["chat_type"] = "private"
    # Telegram (8.0) computes `hash` over everything except `hash` and `signature`
    dcs = "\n".join(f"{k}={f[k]}" for k in sorted(f))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    f["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    f["signature"] = "abc_ed25519_sig_-_"
    r = client.post(URL, {"init_data": urlencode(f)}, format="json")
    assert r.status_code == 200, r.data


# --- happy path ---------------------------------------------------------
def test_valid_initdata_creates_linked_user_and_issues_jwt(client, sales_bot):
    r = client.post(URL, {"init_data": _sign(_fields(tg_id=42))}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["created"] is True
    assert r.data["access"] and r.data["refresh"]

    u = User.objects.get(telegram_id=42)
    assert u.source == Source.BOT
    assert u.username.startswith("tg_")
    assert u.telegram_username == "tg_user"

    # the issued token behaves as a normal customer token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
    assert client.get("/api/v1/auth/me/").data["telegram_id"] == 42
    assert client.get("/api/v1/services/").status_code == 200


def test_second_launch_links_the_same_user(client, sales_bot):
    existing = User.objects.create_user("olduser", "x", telegram_id=999, source=Source.SITE)
    r = client.post(URL, {"init_data": _sign(_fields(tg_id=999))}, format="json")
    assert r.status_code == 200
    assert r.data["created"] is False
    assert r.data["user"]["id"] == existing.id
    assert User.objects.filter(telegram_id=999).count() == 1


def test_miniapp_session_has_no_admin_access(client, sales_bot):
    r = client.post(URL, {"init_data": _sign(_fields())}, format="json")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
    # a plain customer JWT must not reach the staff API
    assert client.get("/api/v1/admin/users/").status_code in (401, 403)


# --- rejection paths --------------------------------------------------
def test_forged_hash_is_rejected(client, sales_bot):
    fields = _fields()
    fields["hash"] = "deadbeef" * 8  # 64 hex chars, but wrong
    r = client.post(URL, {"init_data": urlencode(fields)}, format="json")
    assert r.status_code == 401
    assert not User.objects.exists()


def test_signed_with_wrong_token_is_rejected(client, sales_bot):
    bad = _sign(_fields(), token="000000:attacker-token")
    r = client.post(URL, {"init_data": bad}, format="json")
    assert r.status_code == 401


def test_tampered_payload_after_signing_is_rejected(client, sales_bot):
    # sign for id=101010, then flip the id in the (still-encoded) string,
    # keeping the now-stale hash
    signed = _sign(_fields(tg_id=101010))
    tampered = signed.replace("101010", "202020")
    assert tampered != signed
    r = client.post(URL, {"init_data": tampered}, format="json")
    assert r.status_code == 401
    assert not User.objects.filter(telegram_id=202020).exists()


def test_expired_auth_date_is_rejected(client, sales_bot, settings):
    settings.MINIAPP_INITDATA_MAX_AGE = 3600
    old = _sign(_fields(auth_date=time.time() - 7200))
    r = client.post(URL, {"init_data": old}, format="json")
    assert r.status_code == 401
    assert "expired" in r.data["detail"]


def test_missing_hash_is_rejected(client, sales_bot):
    r = client.post(URL, {"init_data": urlencode(_fields())}, format="json")
    assert r.status_code == 401


def test_empty_initdata_is_rejected(client, sales_bot):
    assert client.post(URL, {"init_data": ""}, format="json").status_code == 400


def test_no_sales_bot_configured_returns_503(client):
    r = client.post(URL, {"init_data": _sign(_fields())}, format="json")
    assert r.status_code == 503


def test_disabled_account_cannot_start_a_session(client, sales_bot):
    User.objects.create_user("banned", "x", telegram_id=555, source=Source.BOT, is_active=False)
    r = client.post(URL, {"init_data": _sign(_fields(tg_id=555))}, format="json")
    assert r.status_code == 403
