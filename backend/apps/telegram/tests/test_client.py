import pytest
import responses

from apps.telegram.client import TelegramClient, TelegramError

API = "https://api.telegram.org/bottok"


@responses.activate
def test_send_message_ok():
    responses.add(responses.POST, f"{API}/sendMessage", json={"ok": True, "result": {"message_id": 7}})
    assert TelegramClient("tok").send_message(1, "hi")["message_id"] == 7


@responses.activate
def test_api_error_raises():
    responses.add(responses.POST, f"{API}/sendMessage",
                  json={"ok": False, "description": "chat not found"}, status=400)
    with pytest.raises(TelegramError):
        TelegramClient("tok").send_message(1, "hi")


@responses.activate
def test_is_member_true_false():
    responses.add(responses.POST, f"{API}/getChatMember", json={"ok": True, "result": {"status": "member"}})
    assert TelegramClient("tok").is_member("@c", 5) is True

    responses.replace(responses.POST, f"{API}/getChatMember",
                      json={"ok": True, "result": {"status": "left"}})
    assert TelegramClient("tok").is_member("@c", 5) is False


@responses.activate
def test_is_member_swallows_errors():
    responses.add(responses.POST, f"{API}/getChatMember",
                  json={"ok": False, "description": "bot is not a member"}, status=400)
    assert TelegramClient("tok").is_member("@c", 5) is False
