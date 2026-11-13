"""v1.60.1 — store bot fixes.

1) Telegram could never deliver to a store bot: the webhook URL is on our domain, which resolves to the Iran tunnel IP
   («Connection refused»). The webhook now carries `ip_address` = SERVER_IP and the check puts it back; /start always answers.
2) The phone flow end to end in a store bot (request_contact button, own number only, linking in the store).
3) «اشتراک شماره تلفن اجباری باشد» per store: bot, Mini App, site sign-up.
4) Mandatory channels per store (only where the bot is admin; none = off), Mini App too.
5) Store staff link their Telegram (numeric id + confirm button) and decide payments from the store bot; never ours.
"""
import json

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Staff, User
from apps.settings_app.utils import set_setting
from apps.telegram.models import RequiredChannel
from apps.tenancy import bots, context
from apps.tenancy import staff as S
from apps.tenancy.models import TenantBot
from apps.tenancy.tests.test_phase6 import (  # noqa: F401
    HOST, STORE_TOKEN, TG, _init, _update, boss, connected, ours, store, tg, wire)
from apps.tenancy.tests.test_phase8 import _client

pytestmark = pytest.mark.django_db
IP = "46.62.192.189"


def _texts(wire):
    return [str(p.get("text", "")) for _, m, p in wire if m in ("sendMessage", "editMessageText")]


def _markups(wire):
    return [json.loads(p["reply_markup"]) for _, m, p in wire if m == "sendMessage" and p.get("reply_markup")]


# ------------------------------------------------------------------ 1) delivery + /start
def test_webhook_goes_straight_to_our_server_ip(connected, tg, settings):
    settings.SERVER_IP = IP
    tg.calls.clear()
    bots.apply(connected)
    hook = [p for _, m, p in tg.calls if m == "setWebhook"][-1]
    assert hook["ip_address"] == IP and hook["url"] == bots.hook_url(connected.tenant_id)
    # Telegram still resolving our domain (no / another ip) → the check sets it again
    tg.calls.clear()
    tg.webhook_info = {"url": bots.hook_url(connected.tenant_id), "pending_update_count": 4, "ip_address": "185.124.174.13"}
    bots.check(TenantBot.objects.get(pk=connected.pk))
    assert "setWebhook" in tg.methods(STORE_TOKEN)


def test_start_always_answers_even_when_a_step_fails(connected, store, wire, monkeypatch):
    from apps.telegram.bot import screens
    from apps.telegram.tasks import store_bot_update_task

    monkeypatch.setattr(screens, "main_menu", lambda user: (_ for _ in ()).throw(RuntimeError("boom")))
    store_bot_update_task(store.pk, _update("/start"))
    assert any("فروشگاه شش" in t for t in _texts(wire))                     # the welcome / fallback still went out


# ------------------------------------------------------------------ 2) + 3) phone flow in a store bot
def test_store_phone_flow_end_to_end(connected, store, wire):
    from apps.telegram.tasks import store_bot_update_task

    with context.tenant_context(store.pk):
        set_setting("force_share_phone", "true", "bool")
    store_bot_update_task(store.pk, _update("/start"))
    with context.tenant_context(store.pk):
        assert not User.objects.filter(telegram_id=TG).exists()               # no account before the phone
    kb = [m for m in _markups(wire) if "keyboard" in m]
    assert kb and kb[-1]["keyboard"][0][0].get("request_contact") is True     # «ارسال شماره»
    other = {"update_id": 9101, "message": {"message_id": 5, "date": 0, "chat": {"id": TG, "type": "private"},
             "from": {"id": TG, "is_bot": False, "first_name": "Sara"},
             "contact": {"phone_number": "+989121112233", "first_name": "X", "user_id": TG + 1}}}
    store_bot_update_task(store.pk, other)                                    # someone else's card → refused
    with context.tenant_context(store.pk):
        assert not User.objects.filter(telegram_id=TG).exists()
    own = json.loads(json.dumps(other))
    own["update_id"], own["message"]["contact"]["user_id"] = 9102, TG
    store_bot_update_task(store.pk, own)
    with context.tenant_context(store.pk):
        u = User.objects.get(telegram_id=TG)
        assert u.phone == "09121112233" and u.tenant_id == store.pk
    assert not User.objects.filter(telegram_id=TG).exists()                   # never one of OUR customers


def test_phone_setting_is_per_store_and_reaches_site_and_mini_app(connected, store):
    url = "/api/v1/auth/telegram/miniapp/"
    with context.tenant_context(store.pk):
        set_setting("force_share_phone", "true", "bool")
    r = APIClient(HTTP_HOST=HOST).post(url, {"init_data": _init(STORE_TOKEN)}, format="json")
    assert r.status_code == 403 and r.json()["code"] == "phone_required"
    cfg = APIClient(HTTP_HOST=HOST).get("/api/v1/config/").json()
    assert cfg["phone_required"] is True and cfg["bot_username"] == connected.username
    assert APIClient().get("/api/v1/config/").json()["phone_required"] is False          # ours untouched
    with context.tenant_context(store.pk):
        from apps.accounts.phone import PhoneError, clean_site_phone, iran_phone_only  # noqa: F401

        set_setting("iran_phone_only", "false", "bool")
        with pytest.raises(PhoneError):
            clean_site_phone("")                                                     # sign-up needs a phone now


# ------------------------------------------------------------------ 4) channels per store
def _store_owner(t, codes=("settings.manage", "payment.approve", "payment.view", "tickets.view")):
    for c in codes:
        Permission.objects.get_or_create(code=c, defaults={"name": c})
    S.set_ceiling(t, list(codes))
    owner, _ = S.ensure_owner(t, f"own-{t.slug}")
    return owner


def test_store_channels_enforced_only_where_its_bot_is_admin(connected, store, tg, monkeypatch):
    from apps.telegram.client import TelegramClient
    from apps.telegram.gate import missing_channel_memberships

    owner = _store_owner(store)
    c = _client(owner, HOST)
    member = {"@good": False, "@nobot": False}
    admin_of = {"@good"}

    def fake(self, method, **kw):
        tg.calls.append((self._base.rsplit("/bot", 1)[1], method, kw))
        if method == "getMe":
            return {"id": 555000111, "is_bot": True, "username": "store_bot"}
        if method == "getChat":
            return {"title": kw["chat_id"].lstrip("@").upper()}
        if method == "getChatMemberCount":
            return 42
        if method == "getChatMember":
            if kw["user_id"] == 555000111:
                return {"status": "administrator" if kw["chat_id"] in admin_of else "left"}
            return {"status": "member" if member.get(kw["chat_id"]) else "left"}
        return True
    monkeypatch.setattr(TelegramClient, "_call", fake)
    assert c.post("/api/v1/admin/channels/", {"channel_id": "@good"}, format="json").status_code == 201
    assert c.post("/api/v1/admin/channels/", {"channel_id": "nobot"}, format="json").status_code == 201
    rows = {r["channel_id"]: r for r in c.get("/api/v1/admin/channels/").json()["results"]}
    assert rows["@good"]["bot_is_admin"] is True and rows["@nobot"]["bot_is_admin"] is False
    with context.tenant_context(store.pk):
        assert [ch.channel_id for ch in missing_channel_memberships(TG)] == ["@good"]   # nobot: never locks anyone out
        member["@good"] = True
        assert missing_channel_memberships(TG) == []
    assert not RequiredChannel.objects.exists()                                         # nothing of ours
    member["@good"] = False
    r = APIClient(HTTP_HOST=HOST).post("/api/v1/auth/telegram/miniapp/", {"init_data": _init(STORE_TOKEN)}, format="json")
    assert r.status_code == 403 and r.json()["code"] == "join_channels" and r.json()["channels"][0]["url"] == "https://t.me/good"
    # a store can set only its phone rule, never our join switch; our channels API stays bots.manage
    c.put("/api/v1/admin/channels/enforcement/", {"force_channel_join": True, "force_share_phone": True}, format="json")
    from apps.settings_app.utils import get_setting

    assert get_setting("force_channel_join", False) is False


# ------------------------------------------------------------------ 5) store staff in the store bot
def test_store_staff_link_by_id_and_decide_payments(connected, store, tg, wire):
    from apps.telegram.tasks import store_bot_update_task

    owner = _store_owner(store)
    c = _client(owner, HOST)
    r = c.put("/api/v1/admin/tickets/telegram-link/", {"telegram_id": str(TG)}, format="json")
    assert r.status_code == 200, r.content
    tok, msg = [(t, p) for t, m, p in tg.calls if m == "sendMessage"][-1]
    assert tok == STORE_TOKEN and str(msg["chat_id"]) == str(TG)                # through the STORE's bot, to that id
    markup = msg["reply_markup"] if isinstance(msg["reply_markup"], dict) else json.loads(msg["reply_markup"])
    code = markup["inline_keyboard"][0][0]["callback_data"]
    cb = {"update_id": 9201, "callback_query": {"id": "q", "data": code, "chat_instance": "c",
          "from": {"id": TG, "is_bot": False, "first_name": "Owner"},
          "message": {"message_id": 3, "date": 0, "chat": {"id": TG, "type": "private"}}}}
    store_bot_update_task(store.pk, cb)
    owner.refresh_from_db()
    assert owner.telegram_id == TG
    # an approve button → a question → yes → approve_payment as that staff member
    from apps.payments_sms.models import Payment, PaymentStatus
    with context.tenant_context(store.pk):
        pay = _store_payment()
    for data, uid in ((f"py:a:{pay.id}", 9202), (f"py:A:{pay.id}", 9203)):
        store_bot_update_task(store.pk, {**cb, "update_id": uid, "callback_query": {**cb["callback_query"], "data": data}})
    with context.tenant_context(store.pk):
        assert Payment.objects.get(pk=pay.pk).status == PaymentStatus.APPROVED
    # our staff with the same kind of button in a store bot → refused
    Staff.objects.create(username="ours-op", is_superadmin=True, telegram_id=TG + 5)
    wire.clear()
    store_bot_update_task(store.pk, {**cb, "update_id": 9204, "callback_query": {
        **cb["callback_query"], "data": f"py:A:{pay.id}", "from": {"id": TG + 5, "is_bot": False, "first_name": "Us"}}})
    assert any("⛔️" in t for t in _texts(wire))


def _store_payment():
    from datetime import timedelta
    from decimal import Decimal

    from django.utils import timezone

    from apps.orders.models import Order, OrderStatus, OrderType
    from apps.payments_sms.models import Payment, PaymentStatus
    from apps.plans.models import Plan

    u = User.objects.create_user("payer1", "Str0ngPass!")
    plan = Plan.objects.create(name_fa="p", price=Decimal(100000), duration_days=30)
    o = Order.objects.create(user=u, plan=plan, type=OrderType.NEW, status=OrderStatus.PENDING_PAYMENT, amount=Decimal(100000),
                             amount_unique=Decimal(100321), unique_expire_at=timezone.now() + timedelta(minutes=10))
    return Payment.objects.create(order=o, amount=Decimal(100321), status=PaymentStatus.PENDING, method="card_manual")
