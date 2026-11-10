"""Multi-tenant Phase 6 (v1.49): a store's own Telegram bot (webhook) + Mini App per store.

* Only our staff set / replace / remove the token (getMe, never our bots, one store per bot, encrypted, never returned).
* Telegram → /api/v1/telegram/hook/<id>/ on OUR host: secret header, dedupe, suspended store dropped, store domains 404.
* An update runs the sales bot's handlers inside the store: its customers, its token, its Mini App; staff flows are off.
* `sales_client()` follows the store; staff / platform alerts always use our bot.
* The Mini App on a store's domain is signed with the store's token (ours is refused there).
"""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import Staff, User
from apps.common.models import AuditLog
from apps.payments_sms.tests.test_blu import staff_client
from apps.telegram.models import BotType, TelegramConfig
from apps.tenancy import bots, context
from apps.tenancy.models import Tenant, TenantBot, TenantDomain

pytestmark = pytest.mark.django_db
HOST = "shop-p6.example"
OURS = "111222333:" + "B" * 35
STORE_TOKEN = "555000111:" + "S" * 35
OTHER_TOKEN = "555000222:" + "O" * 35
TG = 880011
HOOK = "/api/v1/telegram/hook/{}/"
ADMIN = "/api/v1/admin/agency/panel-admins/p6admin/store/"


# ------------------------------------------------------------------ fixtures
class FakeTelegram:
    """Every TelegramClient call: (token, method, params). getMe answers from the token's id."""

    def __init__(self):
        self.calls, self.webhook_info, self.fail = [], None, set()

    def __call__(self, client, method, *, files=None, http_timeout=None, **params):
        from apps.telegram.client import TelegramError

        token = client._base.rsplit("/bot", 1)[1]
        self.calls.append((token, method, params))
        if method in self.fail:
            raise TelegramError(f"{method}: Unauthorized")
        if method == "getMe":
            bid = int(token.split(":")[0])
            return {"id": bid, "is_bot": True, "username": f"store{bid}_bot"}
        if method == "getWebhookInfo":
            return self.webhook_info or {"url": bots.hook_url(Tenant.objects.get(slug="s6").pk), "pending_update_count": 0}
        if method == "sendMessage":
            return {"message_id": 1}
        return True

    def methods(self, token=None):
        return [m for t, m, _ in self.calls if token is None or t == token]


@pytest.fixture
def tg(monkeypatch):
    fake = FakeTelegram()
    from apps.telegram.client import TelegramClient

    monkeypatch.setattr(TelegramClient, "_call", lambda self, method, **kw: fake(self, method, **kw))
    return fake


@pytest.fixture
def ours(_default_tenant):
    TelegramConfig.objects.create(bot_type=BotType.SALES, token=OURS, is_active=True)


@pytest.fixture
def store(ours):
    t = Tenant.objects.create(slug="s6", name="Store Six", status="active", reseller_username="p6admin")
    TenantDomain.objects.create(tenant=t, host=HOST, state="active")
    from apps.settings_app.models import TenantBranding

    with context.tenant_context(t.pk):
        TenantBranding.objects.create(site_name_fa="فروشگاه شش", site_name_en="Store Six", bot_description_fa="ربات فروشگاه شش")
    cache.clear()
    return t


@pytest.fixture
def boss():
    return staff_client("super", "p6-boss")


@pytest.fixture
def connected(store, tg, boss):
    r = boss.post(ADMIN + "bot/", {"token": STORE_TOKEN}, format="json")
    assert r.status_code == 200, r.content
    tg.calls.clear()
    return TenantBot.objects.get(tenant=store)


# ------------------------------------------------------------------ token (our staff only)
def test_our_staff_connect_a_store_bot_and_the_token_never_comes_back(store, tg, boss):
    for bad, code in (("nope", "format"), (OURS, "ours")):
        r = boss.post(ADMIN + "bot/", {"token": bad}, format="json")
        assert r.status_code == 400 and r.json()["code"] == code
    tg.fail = {"getMe"}
    assert boss.post(ADMIN + "bot/", {"token": STORE_TOKEN}, format="json").json()["code"] == "rejected"
    tg.fail = set()
    r = boss.post(ADMIN + "bot/", {"token": STORE_TOKEN}, format="json")
    assert r.status_code == 200, r.content
    assert STORE_TOKEN not in r.content.decode() and r.json()["store"]["bot"]["username"] == "store555000111_bot"
    b = TenantBot.objects.get(tenant=store)
    hook = [p for t, m, p in tg.calls if m == "setWebhook"][0]
    assert hook["url"] == bots.hook_url(store.pk) and hook["url"].endswith(f"/api/v1/telegram/hook/{store.pk}/")
    assert HOST not in hook["url"]                                                     # OUR host, never the store's
    assert hook["secret_token"] == b.webhook_secret and json.loads(hook["allowed_updates"]) == ["message", "callback_query"]
    menu = [p for t, m, p in tg.calls if m == "setChatMenuButton"][0]
    assert json.loads(menu["menu_button"])["web_app"]["url"] == f"https://{HOST}/"     # the store's Mini App, not ours
    assert [p for t, m, p in tg.calls if m == "setMyDescription"][0]["description"] == "ربات فروشگاه شش"
    assert {t for t, m, _ in tg.calls if m != "getMe"} == {STORE_TOKEN}
    log = AuditLog.objects.get(action="store.bot_set")
    assert STORE_TOKEN not in json.dumps(log.detail) and log.detail["username"] == "store555000111_bot"
    # replace: the old bot stops calling us; remove: webhook deleted, row gone
    tg.calls.clear()
    assert boss.post(ADMIN + "bot/", {"token": OTHER_TOKEN}, format="json").status_code == 200
    assert ("deleteWebhook" in tg.methods(STORE_TOKEN)) and TenantBot.objects.get(tenant=store).bot_id == 555000222
    assert boss.delete(ADMIN + "bot/").status_code == 200
    assert "deleteWebhook" in tg.methods(OTHER_TOKEN) and not TenantBot.objects.filter(tenant=store).exists()
    assert AuditLog.objects.filter(action="store.bot_removed").exists()


def test_one_bot_per_store_and_only_on_our_panel(store, tg, boss):
    other = Tenant.objects.create(slug="s6b", name="Other", status="active", reseller_username="other6")
    TenantBot.objects.create(tenant=other, token=STORE_TOKEN, bot_id=555000111, username="x")
    r = boss.post(ADMIN + "bot/", {"token": STORE_TOKEN}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "taken"
    boss.defaults["HTTP_HOST"] = HOST                      # a store's own panel never reaches the agency API
    assert boss.post(ADMIN + "bot/", {"token": OTHER_TOKEN}, format="json").status_code in (403, 404)


# ------------------------------------------------------------------ webhook
def test_hook_checks_the_secret_dedupes_and_runs_in_the_store(connected, store, monkeypatch):
    from apps.telegram import tasks

    queued = []
    monkeypatch.setattr(tasks.store_bot_update_task, "delay",
                        lambda tid, upd: queued.append((tid, upd["update_id"], context.store_id())))
    c = APIClient()
    url = HOOK.format(store.pk)
    upd = {"update_id": 9001, "message": {"message_id": 1}}
    assert c.post(url, upd, format="json").status_code == 403
    assert c.post(url, upd, format="json", HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="wrong").status_code == 403
    assert c.post(HOOK.format(999999), upd, format="json", HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="x").status_code == 403
    ok = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": connected.webhook_secret}
    assert c.post(url, upd, format="json", **ok).status_code == 200
    assert c.post(url, upd, format="json", **ok).status_code == 200          # Telegram's retry: queued once
    assert queued == [(store.pk, 9001, store.pk)]
    connected.refresh_from_db()
    assert connected.last_update_at is not None
    assert APIClient(HTTP_HOST=HOST).post(url, upd, format="json", **ok).status_code == 404     # our host only
    Tenant.objects.filter(pk=store.pk).update(status=Tenant.SUSPENDED)
    assert c.post(url, {"update_id": 9002}, format="json", **ok).status_code == 200
    assert len(queued) == 1                                                  # a suspended store's bot is silent


def _update(text, uid=1):
    return {"update_id": 7000 + uid, "message": {
        "message_id": uid, "date": int(time.time()), "text": text,
        "chat": {"id": TG, "type": "private"}, "from": {"id": TG, "is_bot": False, "first_name": "Sara", "username": "sara"},
        **({"entities": [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]} if text.startswith("/") else {})}}


@pytest.fixture
def wire(monkeypatch):
    """telebot's own HTTP layer (store bots are real TeleBot objects) — (token, method, params)."""
    import telebot.apihelper as api

    sent = []

    def make_request(token, method_name, method="get", params=None, files=None):
        sent.append((token, method_name, params or {}))
        if method_name in ("sendMessage", "editMessageText"):
            return {"message_id": len(sent), "date": 0, "chat": {"id": TG, "type": "private"}, "text": "x"}
        return True

    monkeypatch.setattr(api, "_make_request", make_request)
    from apps.telegram.bot import sales_bot

    monkeypatch.setattr(sales_bot, "close_old_connections", lambda: None)
    return sent


def test_a_store_update_makes_a_store_customer_and_answers_with_the_store_bot(connected, store, wire):
    from apps.telegram.tasks import store_bot_update_task

    assert store_bot_update_task(store.pk, _update("/start")) is True
    with context.tenant_context(store.pk):
        u = User.objects.get(telegram_id=TG)
    assert not User.objects.filter(telegram_id=TG).exists()                  # not one of OUR customers
    assert wire and {t for t, _, _ in wire} == {STORE_TOKEN}
    texts = " ".join(str(p.get("text", "")) for _, m, p in wire if m == "sendMessage")
    assert "فروشگاه شش" in texts                                              # the store's name, its welcome
    apps_ = [b["web_app"]["url"] for _, m, p in wire if p.get("reply_markup")
             for row in json.loads(p["reply_markup"]).get("inline_keyboard", []) for b in row if "web_app" in b]
    assert apps_ and set(apps_) == {f"https://{HOST}/"}                     # the Mini App button = the store's domain
    assert u.tenant_id == store.pk


def test_staff_flows_never_run_in_a_store_bot(connected, store, wire, monkeypatch):
    from apps.telegram.tasks import store_bot_update_task
    from apps.tickets import bot as tbot
    from apps.tickets import staff_link

    op = Staff.objects.create(username="our-op", is_superadmin=True, telegram_id=TG)
    code = staff_link.new_code(Staff.objects.create(username="our-op2", is_superadmin=True))
    store_bot_update_task(store.pk, _update(f"/start staff-{code}", 1))
    assert Staff.objects.get(username="our-op2").telegram_id is None          # our staff never link through a store's bot
    assert op.telegram_id == TG
    cb = {"update_id": 7999, "callback_query": {"id": "q1", "data": "st:l:o:0", "chat_instance": "c",
                                                 "from": {"id": TG, "is_bot": False, "first_name": "Op"},
                                                 "message": {"message_id": 3, "date": 0, "chat": {"id": TG, "type": "private"}}}}
    wire.clear()
    store_bot_update_task(store.pk, cb)
    answers = [str(p.get("text", "")) for _, m, p in wire if m in ("sendMessage", "editMessageText")]
    assert all("⛔️" in a for a in answers)                                   # v1.52: refused — never our staff inbox
    with context.tenant_context(store.pk):
        assert tbot.staff_for(TG) is None
    assert tbot.staff_for(TG) is not None                                     # in our own bot it still works


def test_step_state_is_per_store():
    from apps.telegram.bot import sales_bot

    cache.clear()
    sales_bot.set_state(TG, awaiting="name")
    t = Tenant.objects.create(slug="s6c", name="C", status="active", reseller_username="c6")
    with context.tenant_context(t.pk):
        assert sales_bot.get_state(TG) == {}
        sales_bot.set_state(TG, awaiting="gb")
    assert sales_bot.get_state(TG)["awaiting"] == "name"


# ------------------------------------------------------------------ which bot talks
def test_customer_messages_follow_the_store_staff_alerts_stay_ours(connected, store, tg, monkeypatch):
    from apps.common.staff_alert import alert_staff
    from apps.telegram.config import our_sales_client, sales_client

    assert sales_client()._base.endswith(OURS)
    with context.tenant_context(store.pk):
        assert sales_client()._base.endswith(STORE_TOKEN)
        assert our_sales_client()._base.endswith(OURS)
        Staff.objects.create(username="our-p6", is_superadmin=True, telegram_id=4242)
        tg.calls.clear()
        alert_staff("quota", perm="agency.manage", platform=True)
    assert [(t, p["chat_id"]) for t, m, p in tg.calls if m == "sendMessage"] == [(OURS, 4242)]
    bare = Tenant.objects.create(slug="s6d", name="No bot", status="active", reseller_username="d6")
    with context.tenant_context(bare.pk):
        assert sales_client() is None                                        # never our bot for a store's customer


# ------------------------------------------------------------------ Mini App per store
def _init(token, tg_id=TG):
    fields = {"auth_date": str(int(time.time())), "query_id": "Q",
              "user": json.dumps({"id": tg_id, "first_name": "Sara", "username": "sara"})}
    dcs = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    return urlencode({**fields, "hash": hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()})


def test_mini_app_on_a_store_domain_uses_the_store_bot(store, tg, boss):
    url = "/api/v1/auth/telegram/miniapp/"
    app = APIClient(HTTP_HOST=HOST)
    assert app.post(url, {"init_data": _init(STORE_TOKEN)}, format="json").status_code == 503    # no bot yet
    boss.post(ADMIN + "bot/", {"token": STORE_TOKEN}, format="json")
    assert app.post(url, {"init_data": _init(OURS)}, format="json").status_code == 401          # our bot's session
    r = app.post(url, {"init_data": _init(STORE_TOKEN)}, format="json")
    assert r.status_code == 200, r.content
    with context.tenant_context(store.pk):
        assert User.objects.filter(telegram_id=TG).exists()
    assert not User.objects.filter(telegram_id=TG).exists()
    assert APIClient().post(url, {"init_data": _init(STORE_TOKEN)}, format="json").status_code == 401  # ours: our token


# ------------------------------------------------------------------ health + reseller view
def test_check_puts_the_webhook_back_and_alerts_us_once(connected, store, tg, monkeypatch):
    alerts = []
    monkeypatch.setattr("apps.common.staff_alert.alert_staff", lambda text, **kw: alerts.append((text, kw)) or 1)
    tg.webhook_info = {"url": "https://elsewhere.example/hook", "pending_update_count": 0}
    bots.check(connected)
    assert "setWebhook" in tg.methods(STORE_TOKEN)
    tg.webhook_info = {"url": bots.hook_url(store.pk), "pending_update_count": 4,
                       "last_error_date": int(time.time()) - 60, "last_error_message": "Wrong response from the webhook: 502"}
    bots.check(connected); bots.check(TenantBot.objects.get(pk=connected.pk))
    assert len(alerts) == 1 and "502" in alerts[0][0] and alerts[0][1]["platform"] is True
    tg.webhook_info = None
    bots.check(TenantBot.objects.get(pk=connected.pk))
    assert len(alerts) == 2 and alerts[1][1]["silent"] is True


def test_the_reseller_sees_which_bot_but_never_the_token(connected, store):
    reseller_view = staff_client("super", "p6-store")
    reseller_view.defaults["HTTP_HOST"] = HOST
    r = reseller_view.get("/api/v1/admin/dashboard/")
    assert r.status_code == 200, r.content
    assert r.json()["bot"]["username"] == "store555000111_bot" and r.json()["bot"]["state"] == "ok"
    assert STORE_TOKEN not in r.content.decode() and connected.webhook_secret not in r.content.decode()
