"""Sales bot screens + router, driven through the real handlers on a fake bot
(no network, never the live bot): every screen, edit-in-place, the purchase
flow (rules → invoice → receipt), services, history, account, pages."""
import json
import re
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest
from django.core.cache import cache
from django.utils import timezone
from telebot import types

from apps.accounts.models import User
from apps.orders.models import Order, OrderStatus
from apps.panel.models import Panel, Service
from apps.payments_sms.models import BankCard, Payment, PaymentStatus
from apps.plans.models import Plan
from apps.settings_app.models import Page, SiteConfig
from apps.telegram.bot import sales_bot
from apps.telegram.bot import screens as sc

pytestmark = pytest.mark.django_db
TG = 7070
def _png():
    import io
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (20, 30), (240, 240, 240)).save(buf, "PNG")
    return buf.getvalue()


PNG_BROKEN = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4"
       b"\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82")


class FakeBot:
    """Records every outbound call; mirrors telebot's handler matching."""

    def __init__(self):
        self.msg_handlers, self.cb_handlers, self.out = [], [], []

    def message_handler(self, commands=None, content_types=None, func=None):
        def deco(fn):
            self.msg_handlers.append((commands, content_types or ["text"], func, fn)); return fn
        return deco

    def callback_query_handler(self, func=None):
        def deco(fn):
            self.cb_handlers.append((func, fn)); return fn
        return deco

    def send_message(self, chat_id, text, reply_markup=None, **kw):
        self.out.append(("send", text, reply_markup)); return NS(message_id=len(self.out))

    def edit_message_text(self, text, chat_id, message_id, reply_markup=None, **kw):
        self.out.append(("edit", text, reply_markup))

    def send_photo(self, chat_id, photo, caption=None, reply_markup=None, **kw):
        self.out.append(("photo", caption, reply_markup))

    def delete_message(self, chat_id, message_id):
        self.out.append(("delete", message_id, None))

    def answer_callback_query(self, *a, **kw):
        pass

    def get_file(self, file_id):
        return NS(file_path="photos/r.png")

    def download_file(self, path):
        return _png()

    def feed(self, msg):
        self.out.clear()
        for commands, ctypes, func, fn in self.msg_handlers:
            if msg.content_type not in ctypes:
                continue
            text = msg.text or ""
            if commands and not (text.startswith("/") and text.split()[0].lstrip("/").split("@")[0] in commands):
                continue
            if func and not func(msg):
                continue
            fn(msg); return self.out
        raise AssertionError("no handler")

    def click(self, data, message_id=11, content_type="text"):
        self.out.clear()
        c = NS(id="cb", data=data, from_user=_from(),
               message=NS(chat=NS(id=TG), message_id=message_id, content_type=content_type))
        for func, fn in self.cb_handlers:
            if func is None or func(c):
                fn(c); return self.out


def _from():
    return NS(id=TG, username="u", first_name="Ali", last_name="")


def _msg(text=None, content_type="text", **extra):
    base = dict(content_type=content_type, text=text, chat=NS(id=TG), from_user=_from(), message_id=5,
                photo=None, document=None, contact=None)
    base.update(extra)
    return NS(**base)


def _cb_datas(markup):
    if markup is None:
        return []
    return [b["callback_data"] for row in _rows(markup) for b in row if "callback_data" in b]


def _datas(markup):
    if markup is None:
        return []
    kb = json.loads(markup.to_json())["inline_keyboard"] if isinstance(markup, types.InlineKeyboardMarkup) else []
    return [b.get("callback_data") or b.get("url") or "web_app" for row in kb for b in row]


def _rows(markup):
    return json.loads(markup.to_json())["inline_keyboard"]


@pytest.fixture(autouse=True)
def _env(monkeypatch, settings):
    monkeypatch.setattr(sales_bot, "close_old_connections", lambda: None)
    settings.MINIAPP_URL = "https://app.example.ir/"
    cache.clear()
    from apps.orders import tasks
    monkeypatch.setattr(tasks.fulfill_order, "delay", lambda *_: None)
    import apps.panel.services as ps
    monkeypatch.setattr(ps, "refresh_watchable_services", lambda svcs: False)


@pytest.fixture
def bot():
    b = FakeBot()
    sales_bot._register(b)
    return b


@pytest.fixture
def user():
    return User.objects.create_user("tgu", "Str0ngPass!", telegram_id=TG, phone="09120000000",
                                    terms_accepted_at=timezone.now())


@pytest.fixture
def plans():
    BankCard.objects.create(card_number="6037991234567890", holder_name="پویا", is_active=True)
    a = Plan.objects.create(name_fa="اقتصادی 30", name_en="Economy 30", category_fa="ماهانه", category_en="Monthly",
                            price=Decimal("95000"), data_limit=30 * 1024**3, duration_days=30, sort_order=1)
    b = Plan.objects.create(name_fa="سه‌ماهه", name_en="Quarterly", category_fa="سه‌ماهه", category_en="Quarterly",
                            price=Decimal("420000"), data_limit=150 * 1024**3, duration_days=90, sort_order=2)
    c = Plan.objects.create(name_fa="حجمی", name_en="Custom", type="custom_volume", category_fa="ماهانه",
                            price=Decimal("0"), price_per_gb=Decimal("2900"), min_gb=10, max_gb=200, duration_days=30)
    return a, b, c


def _all_screens(user, plans):
    a, *_ = plans
    return [sc.main_menu(user), sc.store(user), sc.category(user, 0), sc.plan_detail(user, a), sc.terms(user),
            sc.services(user), sc.history(user), sc.account(user), sc.rules(user), sc.guide(user),
            sc.guide_os(user, "ios"), sc.support(user)]


# --- layout / limits -------------------------------------------------------
def test_main_menu_has_everything_two_per_row(user):
    m = sc.main_menu(user)
    rows = _rows(m.markup)
    assert all(len(r) <= 2 for r in rows)
    labels = [b["text"] for r in rows for b in r]
    for want in ("🛒 خرید سرویس", "📦 سرویس‌های من", "🧾 سوابق خرید", "👤 حساب من", "📜 قوانین",
                 "📚 راهنمای اتصال", "💬 پشتیبانی", "🌐 ورود به مینی‌اپ"):
        assert want in labels
    assert any("web_app" in b for r in rows for b in r)


def test_every_callback_fits_and_digits_are_latin(user, plans):
    for s in _all_screens(user, plans):
        for d in _cb_datas(s.markup):          # Telegram's limit is on callback_data
            assert len(d.encode()) <= 64, d
        assert not re.search(r"[۰-۹٠-٩]", s.text), s.text
        assert len(s.text) <= 4096
        # every screen except the menu itself offers a way home
        if s.markup is not None and s is not None and "منوی اصلی" not in s.text:
            assert "m:home" in _datas(s.markup)


# --- edit in place -----------------------------------------------------------
def test_buttons_edit_the_message_instead_of_sending(bot, user, plans):
    out = bot.click("m:buy")
    assert [k for k, *_ in out] == ["edit"]
    out = bot.click("m:home")
    assert out[0][0] == "edit" and "m:buy" in _datas(out[0][2])


def test_qr_replaces_the_text_message_with_a_photo(bot, user):
    svc = Service.objects.create(user=user, panel=Panel.objects.create(name="P", base_url="https://p", admin_username="a",
                                 admin_password_enc="x"), panel_username="ali1", status="active",
                                 subscription_url="https://sub.example/x", data_limit=10 * 1024**3)
    out = bot.click(f"s:{svc.id}:qr")
    assert [k for k, *_ in out] == ["delete", "photo"] and "https://sub.example/x" in out[1][1]
    out = bot.click(f"s:{svc.id}", content_type="photo")        # back from the photo
    assert [k for k, *_ in out] == ["delete", "send"]


# --- purchase flow -----------------------------------------------------------
def test_full_purchase_categories_plan_name_rules_invoice(bot, user, plans):
    a, *_ = plans
    User.objects.filter(pk=user.pk).update(terms_accepted_at=None)
    assert "c:0" in _datas(bot.click("m:buy")[0][2])
    assert f"p:{a.id}" in _datas(bot.click("c:0")[0][2])
    detail = bot.click(f"p:{a.id}")[0][1]
    assert "30 گیگ" in detail and "30 روز" in detail and "95,000 تومان" in detail
    bot.click(f"pb:{a.id}")
    out = bot.feed(_msg("ali2"))
    assert "t:ok" in _datas(out[-1][2])                     # rules first (same as the site)
    out = bot.click("t:ok")
    inv = out[-1][1]
    order = Order.objects.get(user=user)
    assert order.source == "bot" and order.requested_account_name == "ali2"
    assert f"{int(order.amount_unique):,}" in inv and "6037991234567890" in inv and "⏰" in inv
    assert User.objects.get(pk=user.pk).terms_accepted_at is not None


def test_resume_open_order_like_the_site(bot, user, plans):
    a, *_ = plans
    bot.click(f"pb:{a.id}"); bot.feed(_msg("ali3"))
    first = Order.objects.get(user=user)
    assert f"o:{first.id}" in _datas(sc.main_menu(user).markup)       # "continue open order"
    bot.click(f"pb:{a.id}"); out = bot.feed(_msg("ali3"))
    assert Order.objects.filter(user=user).count() == 1
    assert "سفارش باز قبلی" in out[-1][1]


def test_custom_volume_validates_then_continues(bot, user, plans):
    *_, c = plans
    bot.click(f"pb:{c.id}")
    assert "بین 10 و 200" in bot.feed(_msg("5"))[-1][1]
    assert "نام" in bot.feed(_msg("۵۰"))[-1][1]             # Persian digits accepted
    bot.feed(_msg("vol1"))
    assert Order.objects.get(user=user).custom_volume_gb == 50


def test_taken_account_name_asks_again(bot, user, plans):
    a, *_ = plans
    panel = Panel.objects.create(name="P2", base_url="https://p2", admin_username="a", admin_password_enc="x")
    Service.objects.create(user=user, panel=panel, panel_username="taken", status="active")
    Plan.objects.filter(pk=a.pk).update(panel=panel)
    bot.click(f"pb:{a.id}")
    out = bot.feed(_msg("taken"))
    assert "⚠️" in out[-1][1] and not Order.objects.exists()
    bot.feed(_msg("free1"))
    assert Order.objects.filter(requested_account_name="free1").exists()


def test_paid_order_with_taken_name_asks_for_a_new_one(bot, user, plans):
    """the "choose another name" button from the fulfilment message: taken names are refused, a free one is saved"""
    a, *_ = plans
    panel = Panel.objects.create(name="P3", base_url="https://p3.invalid", admin_username="a", admin_password_enc="x")
    Plan.objects.filter(pk=a.pk).update(panel=panel)
    Service.objects.create(user=user, panel=panel, panel_username="taken2", status="active")
    o = Order(user=user, plan_id=a.id, type="new", requested_account_name="parsa", amount=1, amount_unique=1,
              unique_expire_at=timezone.now(), status=OrderStatus.PAID, needs_new_name=True)
    o.save()
    out = bot.click(f"nn:{o.id}")
    assert "✏️" in out[-1][1]
    out = bot.feed(_msg("taken2"))
    assert "⚠️" in out[-1][1]
    out = bot.feed(_msg("fresh9"))
    assert "fresh9" in out[-1][1] and "✅" in out[-1][1]
    o.refresh_from_db()
    assert o.requested_account_name == "fresh9" and not o.needs_new_name
    assert bot.click(f"nn:{o.id}")                       # no longer pending a name → history, nothing asked


def test_receipt_photo_attaches_to_the_open_order(bot, user, plans):
    a, *_ = plans
    bot.click(f"pb:{a.id}"); bot.feed(_msg("ali4"))
    out = bot.feed(_msg(content_type="photo", photo=[NS(file_id="f1")]))
    assert "رسید شما دریافت شد" in out[-1][1]
    assert Payment.objects.get(order__user=user).status == PaymentStatus.PENDING


# --- services / history ----------------------------------------------------------
def test_services_paginated_and_detail_buttons(bot, user):
    panel = Panel.objects.create(name="P", base_url="https://p", admin_username="a", admin_password_enc="x")
    svcs = [Service.objects.create(user=user, panel=panel, panel_username=f"s{i}", status="active",
                                   subscription_url=f"https://sub/{i}", data_limit=10 * 1024**3) for i in range(8)]
    first = bot.click("m:svcs")[0][2]
    assert "m:svcs:1" in _datas(first) and len([d for d in _datas(first) if d.startswith("s:")]) == 6
    assert len([d for d in _datas(bot.click("m:svcs:1")[0][2]) if d.startswith("s:")]) == 2
    d = _datas(bot.click(f"s:{svcs[0].id}")[0][2])
    for want in (":link", ":qr", ":revoke", ":rn"):
        assert any(x.endswith(want) for x in d)
    assert "m:svcs" in d and "m:home" in d


def test_revoke_needs_confirmation(bot, user, monkeypatch):
    panel = Panel.objects.create(name="P", base_url="https://p", admin_username="a", admin_password_enc="x")
    svc = Service.objects.create(user=user, panel=panel, panel_username="r1", status="active", subscription_url="https://sub/old")

    def fake_revoke(sid):
        Service.objects.filter(pk=sid).update(subscription_url="https://sub/new")
        return Service.objects.get(pk=sid)
    monkeypatch.setattr(sales_bot, "revoke_subscription", fake_revoke)
    assert f"s:{svc.id}:revoke:yes" in _datas(bot.click(f"s:{svc.id}:revoke")[0][2])
    out = bot.click(f"s:{svc.id}:revoke:yes")
    assert out[-1][0] == "photo" and "https://sub/new" in out[-1][1]


def test_history_icons_and_reject_reason(bot, user, plans):
    a, *_ = plans
    mk = lambda st: Order.objects.create(user=user, plan=a, amount=1000, amount_unique=1200, status=st,
                                         unique_expire_at=timezone.now() + timedelta(minutes=5))
    done, rej, exp, pend = mk("completed"), mk("rejected"), mk("expired"), mk("pending_payment")
    Payment.objects.create(order=rej, method="card_manual", amount=1200, status="rejected", reject_reason="رسید ناخوانا")
    text = bot.click("m:history")[0][1]
    assert f"✅ <b>سفارش #{done.id}</b> · تکمیل‌شده" in text and f"❌ <b>سفارش #{rej.id}</b> · رد شده" in text
    assert "دلیل: رسید ناخوانا" in text
    assert f"⌛ <b>سفارش #{exp.id}</b> · منقضی" in text and f"⏳ <b>سفارش #{pend.id}</b> · در انتظار" in text
    assert "1,200 تومان" in text and "\n\n" in text


def test_history_shows_paid_amount_account_and_manual_services(bot, user, plans):
    a, *_ = plans
    exp = timezone.now() + timedelta(minutes=5)
    paid = Order.objects.create(user=user, plan=a, amount=250000, amount_unique=250430, status="completed",
                                requested_account_name="pouya_main", unique_expire_at=exp)
    manual = Order.objects.create(user=user, plan=a, type="manual", amount=0, amount_unique=0, status="completed",
                                  requested_account_name="gift1", unique_expire_at=exp)
    text = bot.click("m:history")[0][1]
    assert "250,430 تومان" in text and "<code>pouya_main</code>" in text
    block = text.split(f"#{manual.id}</b>")[1].split("\n\n")[0]
    assert "سرویس دستی (ادمین)" in block and "0 تومان" not in block and "<code>gift1</code>" in block
    assert f"#{paid.id}" in text and "/" in block   # Jalali date with Latin digits
    assert not any("\u06f0" <= ch <= "\u06f9" for ch in text)


# --- account / pages / referral ---------------------------------------------------
def test_account_language_toggle_and_invite_links(bot, user):
    sc.BOT_USERNAME["value"] = "caspinbot"
    text = bot.click("m:acc")[0][1]
    assert user.referral_code in text and f"t.me/caspinbot?start=ref_{user.referral_code}" in text
    out = bot.click("m:lang")
    assert "My account" in out[0][1] and User.objects.get(pk=user.pk).language == "en"
    assert "Main menu" in bot.click("m:home")[0][1]


def test_change_password_deletes_the_message(bot, user):
    bot.click("m:pwd")
    out = bot.feed(_msg("NewPass!2345"))
    assert ("delete", 5, None) in out and "✅" in out[-1][1]
    assert User.objects.get(pk=user.pk).check_password("NewPass!2345")


def test_rules_help_support_from_cms_and_branding(bot, user):
    Page.objects.update_or_create(slug="rules", defaults={"title_fa": "قوانین", "body_fa": "<p>قانون اول</p>", "is_active": True})
    Page.objects.update_or_create(slug="tutorial", defaults={"title_fa": "آموزش", "body_fa": "اول برنامه را نصب کنید", "is_active": True})
    cfg = SiteConfig.load(); cfg.support_telegram = "@caspin_support"; cfg.save()
    assert "قانون اول" in bot.click("m:rules")[0][1] and "<p>" not in bot.click("m:rules")[0][1]
    g = bot.click("m:guide")[0]
    assert "اول برنامه را نصب کنید" in g[1] and "ga:ios" in _datas(g[2])
    assert "Streisand" in bot.click("ga:ios")[0][1]
    s = bot.click("m:help")[0]
    assert "@caspin_support" in s[1] and "https://t.me/caspin_support" in _datas(s[2])


def test_start_with_referral_credits_the_inviter(bot):
    inviter = User.objects.create_user("inv", "Str0ngPass!")
    bot.feed(_msg(f"/start ref_{inviter.referral_code}"))
    assert User.objects.get(telegram_id=TG).referred_by_id == inviter.id


@pytest.mark.parametrize("legacy", ["m:buy", "m:svcs", "m:acc", "m:history", "m:help", "m:pwd"])
def test_old_buttons_in_chat_history_still_work(bot, user, plans, legacy):
    out = bot.click(legacy)
    assert out and out[0][0] in ("edit", "send")


def test_bot_support_has_its_own_ids_and_message(bot, user):
    cfg = SiteConfig.load()
    cfg.support_telegram = "@site_support"
    cfg.bot_support_telegram = "@bot_help, https://t.me/bot_help2"
    cfg.bot_support_text_fa = "ساعات کاری: ۹ تا ۲۱ <همه روزه>"
    cfg.save()
    text, kb = bot.click("m:help")[0][1:3]
    assert "ساعات کاری" in text and "&lt;همه روزه&gt;" in text and "@bot_help" in text
    assert "site_support" not in text
    assert [d for d in _datas(kb) if d.startswith("https")] == ["https://t.me/bot_help", "https://t.me/bot_help2"]


def test_bot_support_falls_back_to_site_id(bot, user):
    cfg = SiteConfig.load(); cfg.support_telegram = "caspin"; cfg.bot_support_telegram = ""; cfg.save()
    s = bot.click("m:help")[0]
    assert "@caspin" in s[1] and "https://t.me/caspin" in _datas(s[2])
