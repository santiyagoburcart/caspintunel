"""The sales bot's phone gate (force_share_phone) and contact handling,
exercised through the real handlers registered by `sales_bot._register` on a
fake bot object (no network)."""
from types import SimpleNamespace as NS

import pytest
from telebot import types

from apps.accounts.models import User
from apps.settings_app.utils import set_setting
from apps.telegram.bot import sales_bot

pytestmark = pytest.mark.django_db

TG = 5150


class FakeBot:
    def __init__(self):
        self.msg_handlers, self.cb_handlers, self.sent = [], [], []

    # --- decorator API used by _register --------------------------------
    def message_handler(self, commands=None, content_types=None, func=None):
        def deco(fn):
            self.msg_handlers.append((commands, content_types or ["text"], func, fn))
            return fn
        return deco

    def callback_query_handler(self, func=None):
        def deco(fn):
            self.cb_handlers.append((func, fn))
            return fn
        return deco

    # --- outbound API ------------------------------------------------------
    def send_message(self, chat_id, text, reply_markup=None, **kw):
        self.sent.append((text, reply_markup))
        return NS(chat=NS(id=chat_id), message_id=len(self.sent))

    def edit_message_text(self, text, chat_id, message_id, reply_markup=None, **kw):
        self.sent.append((text, reply_markup))

    def send_photo(self, chat_id, photo, caption=None, reply_markup=None, **kw):
        self.sent.append((caption, reply_markup))

    def register_next_step_handler(self, *a, **kw):
        self.sent.append(("<next-step>", None))

    def answer_callback_query(self, *a, **kw):
        pass

    def delete_message(self, *a, **kw):
        pass

    # --- inbound (mirrors telebot: first matching handler wins) ------------
    def feed(self, msg):
        self.sent.clear()
        for commands, ctypes, func, fn in self.msg_handlers:
            if msg.content_type not in ctypes:
                continue
            if commands and not ((msg.text or "").split() or [""])[0].split("@")[0].lstrip("/") in commands:
                continue
            if commands and not (msg.text or "").startswith("/"):
                continue
            if func and not func(msg):
                continue
            fn(msg)
            return self.sent
        raise AssertionError(f"no handler for {msg.content_type}")

    def click(self, data, tg=TG):
        self.sent.clear()
        c = NS(id="cb", data=data, from_user=_from(tg), message=NS(chat=NS(id=tg)))
        for func, fn in self.cb_handlers:
            if func is None or func(c):
                fn(c)
                return self.sent


def _from(tg=TG):
    return NS(id=tg, username="u", first_name="Ali", last_name="")


def _msg(content_type="text", text=None, tg=TG, **extra):
    return NS(content_type=content_type, text=text, chat=NS(id=tg), from_user=_from(tg),
              message_id=1, photo=None, document=None, contact=None, **extra)


def _contact(phone, owner=TG, tg=TG):
    m = _msg("contact", tg=tg)
    m.contact = NS(phone_number=phone, user_id=owner)
    return m


@pytest.fixture
def bot(monkeypatch):
    # handlers drop stale DB connections per update; inside a test transaction that would kill it
    monkeypatch.setattr(sales_bot, "close_old_connections", lambda: None)
    b = FakeBot()
    sales_bot._register(b)
    return b


def _asks_phone(sent) -> bool:
    return any(isinstance(markup, types.ReplyKeyboardMarkup)
               and "request_contact" in markup.to_json() for _, markup in sent)


def _shows_menu(sent) -> bool:
    return any(isinstance(markup, types.InlineKeyboardMarkup) and "m:buy" in markup.to_json()
               for _, markup in sent)


@pytest.fixture
def force_phone():
    set_setting("force_share_phone", "true", "bool")


@pytest.mark.parametrize("make", [
    lambda: _msg(text="سلام"),
    lambda: _msg(text="/start"),
    lambda: _msg(text="/help"),
    lambda: _msg("sticker"),
    lambda: _msg("voice"),
    lambda: NS(**{**vars(_msg("photo")), "photo": [NS(file_id="f")]}),
])
def test_any_message_without_phone_is_blocked(bot, force_phone, make):
    sent = bot.feed(make())
    assert _asks_phone(sent), sent
    assert not _shows_menu(sent)


@pytest.mark.parametrize("data", ["m:buy", "m:svcs", "m:acc", "m:home", "p:1", "m:pwd"])
def test_any_button_without_phone_is_blocked(bot, force_phone, data):
    bot.feed(_msg(text="/start"))                  # no account yet
    sent = bot.click(data)
    assert _asks_phone(sent)
    assert not _shows_menu(sent) and ("<next-step>", None) not in sent


def test_existing_user_with_phone_is_not_affected(bot, force_phone):
    User.objects.create_user("has_phone", "Str0ngPass!", telegram_id=TG, phone="09121234567")
    sent = bot.feed(_msg(text="hello"))
    assert _shows_menu(sent) and not _asks_phone(sent)
    assert not _asks_phone(bot.click("m:acc"))


def test_gate_off_means_no_prompt(bot):
    sent = bot.feed(_msg(text="/start"))
    assert _shows_menu(sent) and not _asks_phone(sent)


def test_start_creates_no_account_until_the_phone_is_shared(bot, force_phone):
    sent = bot.feed(_msg(text="/start"))
    assert _asks_phone(sent) and any("خوش آمدید" in t for t, _ in sent)
    assert not any("رمز عبور" in t for t, _ in sent)               # no credentials yet
    assert not User.objects.filter(telegram_id=TG).exists()
    bot.click("m:buy")
    bot.feed(_msg(text="hi"))
    assert not User.objects.exists()


def test_sharing_phone_creates_the_account_and_sends_credentials(bot, force_phone):
    bot.feed(_msg(text="/start"))
    sent = bot.feed(_contact("+989351234567"))
    u = User.objects.get(telegram_id=TG)
    assert u.phone == "09351234567"
    assert any("ثبت شد" in t and u.username in t and "رمز عبور" in t for t, _ in sent) and _shows_menu(sent)
    assert _shows_menu(bot.feed(_msg(text="hi")))


def test_referral_from_start_is_applied_when_the_account_is_made(bot, force_phone):
    inviter = User.objects.create_user("inviter", "Str0ngPass!", phone="09121112222")
    bot.feed(_msg(text=f"/start ref_{inviter.referral_code}"))
    assert not User.objects.filter(telegram_id=TG).exists()
    bot.feed(_contact("+989351234567"))
    assert User.objects.get(telegram_id=TG).referred_by_id == inviter.pk


def test_foreign_contact_rejected_and_asked_again(bot, force_phone):
    bot.feed(_msg(text="/start"))
    sent = bot.feed(_contact("+14155552671"))
    assert _asks_phone(sent) and any("ایرانی" in t for t, _ in sent)
    assert not User.objects.filter(telegram_id=TG).exists()
    assert _asks_phone(bot.feed(_msg(text="hi")))          # still gated


def test_someone_elses_contact_is_refused(bot, force_phone):
    site = User.objects.create_user("victim", "Str0ngPass!", phone="09351234567")
    bot.feed(_msg(text="/start"))
    sent = bot.feed(_contact("+989351234567", owner=999))
    assert _asks_phone(sent) and any("شمارهٔ خودتان" in t for t, _ in sent)
    site.refresh_from_db()
    assert site.telegram_id is None and not User.objects.filter(telegram_id=TG).exists()


def test_contact_links_the_site_account_keeping_username_and_password(bot, force_phone):
    site = User.objects.create_user("webuser", "Str0ngPass!", phone="09107323128")
    bot.feed(_msg(text="/start"))
    sent = bot.feed(_contact("+989107323128"))
    assert any("حساب سایت شما به تلگرام متصل شد؛ با همان نام کاربری و رمز قبلی وارد شوید" in t
               and "webuser" in t for t, _ in sent)
    site.refresh_from_db()
    assert site.telegram_id == TG and site.username == "webuser" and site.check_password("Str0ngPass!")
    assert User.objects.count() == 1
    assert _shows_menu(bot.feed(_msg(text="hi")))           # the linked account passes the gate


def test_contact_of_a_number_linked_to_another_telegram_is_refused(bot, force_phone, monkeypatch):
    from apps.telegram import accounts

    monkeypatch.setattr(accounts, "notify_staff_conflict", lambda *a: 0)
    other = User.objects.create_user("webuser", "Str0ngPass!", phone="09107323128", telegram_id=4242)
    bot.feed(_msg(text="/start"))
    sent = bot.feed(_contact("+989107323128"))
    assert any("پشتیبانی" in t for t, _ in sent)
    other.refresh_from_db()
    assert other.telegram_id == 4242 and not User.objects.filter(telegram_id=TG).exists()


def test_gate_off_still_creates_on_start(bot):
    sent = bot.feed(_msg(text="/start"))
    assert any("رمز عبور" in t for t, _ in sent) and User.objects.filter(telegram_id=TG).exists()
