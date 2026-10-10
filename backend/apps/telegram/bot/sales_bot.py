"""
Sales bot wiring (pyTelegramBotAPI, synchronous — pairs naturally with the
Django ORM). Screens live in `bot.screens` (pure, tested); this module routes
Telegram updates onto them and renders each screen by EDITING the current
message in place (no message spam). Typed input (custom volume, account name,
new password) is tracked per user in the cache, so it survives a bot restart.

Handlers are exercised in tests through a fake bot object (no network).
"""
from __future__ import annotations

import html
import logging

import telebot
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.utils import timezone
from telebot import types

from apps.accounts.models import User
from apps.orders.models import Order
from apps.orders.services import OrderError
from apps.panel.exceptions import PanelError
from apps.panel.services import revoke_subscription
from apps.plans.models import Plan, PlanType
from apps.settings_app.models import SiteConfig

from ..accounts import change_password_via_bot, ensure_bot_user, link_telegram_phone
from ..config import get_bot_config
from ..gate import check_access, needs_phone
from ..models import BotType
from ..shop import buy_new, order_awaiting_receipt, renew, submit_bot_receipt
from . import keyboards as kb
from . import screens as sc
from .texts import tr

log = logging.getLogger("caspintunel")
STATE_TTL = 30 * 60


def build_bot() -> telebot.TeleBot | None:
    cfg = get_bot_config(BotType.SALES)
    if not cfg or not cfg.is_active or not cfg.token:
        return None
    if cfg.proxy_url:
        telebot.apihelper.proxy = {"http": cfg.proxy_url, "https": cfg.proxy_url}
    bot = telebot.TeleBot(cfg.token, parse_mode="HTML", threaded=False)
    _register(bot)
    _sync_menu_button(bot)
    try:
        sc.BOT_USERNAME["value"] = bot.get_me().username or ""
    except Exception as exc:  # noqa: BLE001
        log.warning("sales bot: get_me failed: %s", exc)
    return bot


def _sync_menu_button(bot: telebot.TeleBot) -> None:
    """Point the bot's menu button at the Mini App (our user SPA). Idempotent;
    a Telegram hiccup here must not stop the bot."""
    url = sc.miniapp_url()
    if not url:
        return
    try:
        bot.set_chat_menu_button(menu_button=types.MenuButtonWebApp(
            type="web_app", text="🌐 اپ", web_app=types.WebAppInfo(url=url)))
        log.info("sales bot: menu button -> mini app %s", url)
    except Exception as exc:  # noqa: BLE001
        log.warning("sales bot: could not set menu button: %s", exc)


# --- helpers ---------------------------------------------------------
def _user(tg_user):
    user, created, password = ensure_bot_user(
        tg_user.id,
        telegram_username=getattr(tg_user, "username", "") or "",
        name=" ".join(filter(None, [getattr(tg_user, "first_name", ""), getattr(tg_user, "last_name", "")])),
    )
    return user, created, password


def _t(user, fa: str, en: str) -> str:
    return en if getattr(user, "language", "fa") == "en" else fa


def _state_key(tg_id) -> str:
    return f"tgbot:state:{tg_id}"


def get_state(tg_id) -> dict:
    return cache.get(_state_key(tg_id)) or {}


def set_state(tg_id, **values) -> dict:
    st = {**get_state(tg_id), **values}
    cache.set(_state_key(tg_id), st, STATE_TTL)
    return st


def clear_state(tg_id) -> None:
    cache.delete(_state_key(tg_id))


MSG_SHARE_PHONE = (
    "📱 برای ادامه، ابتدا شمارهٔ موبایل خود را با دکمهٔ «اشتراک‌گذاری شماره» در پایین صفحه ارسال کنید.",
    "📱 To continue, please share your phone number using the “Share phone number” button below.",
)
MSG_NOT_IRANIAN = (
    "❌ شمارهٔ این حساب تلگرام ایرانی نیست. فقط شماره‌های موبایل ایرانی (‎+98‎) پذیرفته می‌شوند.\n"
    "لطفاً با حساب تلگرامی که شمارهٔ ایرانی دارد وارد شوید و دوباره شماره را ارسال کنید.",
    "❌ This Telegram account's number is not Iranian. Only Iranian mobile numbers (+98) are accepted.\n"
    "Please use a Telegram account with an Iranian number and share it again.",
)
MSG_NOT_OWN = (
    "لطفاً شمارهٔ خودتان را فقط با دکمهٔ زیر ارسال کنید.",
    "Please share your own number using the button below.",
)
MSG_CONFLICT = (
    "⚠️ این شماره قبلاً به حساب تلگرام دیگری متصل شده است. لطفاً با پشتیبانی تماس بگیرید.",
    "⚠️ This number is already linked to a different Telegram account. Please contact support.",
)
MSG_MERGED = (
    "✅ حساب شما در سایت به ربات متصل شد. برای ورود به سایت، از دکمه «تغییر رمز عبور» در ربات یک رمز جدید تنظیم کنید.",
    "✅ Your website account is now linked to the bot. To sign in on the website, set a new password "
    "with the “Change password” button in the bot.",
)
MSG_PHONE_SAVED = ("شماره ثبت شد ✅", "Phone number saved ✅")


def render(bot, chat_id, screen: sc.Screen, msg=None) -> None:
    """Show a screen: edit the message the button belongs to (text → text);
    a photo screen, or leaving a photo, replaces the message instead."""
    mid = getattr(msg, "message_id", None) if msg is not None else None
    if mid:
        is_text = getattr(msg, "content_type", "text") == "text"
        if screen.photo is None and is_text:
            try:
                bot.edit_message_text(screen.text, chat_id, mid, reply_markup=screen.markup,
                                      parse_mode="HTML", disable_web_page_preview=True)
                return
            except Exception as exc:  # noqa: BLE001
                if "message is not modified" in str(exc):
                    return
        try:
            bot.delete_message(chat_id, mid)
        except Exception:  # noqa: BLE001
            pass
    if screen.photo is not None:
        bot.send_photo(chat_id, screen.photo, caption=screen.text, parse_mode="HTML", reply_markup=screen.markup)
    else:
        bot.send_message(chat_id, screen.text, reply_markup=screen.markup, disable_web_page_preview=True)


def _ask_phone(bot, chat_id, user, reason=MSG_SHARE_PHONE):
    bot.send_message(chat_id, _t(user, *reason), reply_markup=kb.share_phone())


def _enforce_gate(bot, chat_id, user, tg_id, msg=None) -> bool:
    result = check_access(user, tg_id)
    if result.ok:
        return True
    if result.need_phone:
        # the phone comes first: nothing else is reachable until it is shared
        _ask_phone(bot, chat_id, user)
        return False
    if result.missing_channels:
        render(bot, chat_id, sc.join_channels(user, result.missing_channels), msg)
    return False


def _phone_gate(bot, chat_id, user) -> bool:
    if needs_phone(user):
        _ask_phone(bot, chat_id, user)
        return False
    return True


def _apply_referral(user, payload: str) -> None:
    """/start ref_<CODE>: credit the inviter, once, for a brand-new account."""
    code = payload[4:].strip().upper() if payload.startswith("ref_") else ""
    if not code or user.referred_by_id:
        return
    inviter = User.objects.filter(referral_code=code, deleted_at__isnull=True).exclude(pk=user.pk).first()
    if inviter:
        user.referred_by = inviter
        user.save(update_fields=["referred_by", "updated_at"])


# --- purchase flow (shared by buttons and typed input) ---------------------
def _needs_terms(user) -> bool:
    return not getattr(user, "terms_accepted_at", None)


def _place_order(bot, chat_id, user, tg_id, msg=None) -> None:
    """Create the order from the draft in the user's state and show the invoice."""
    st = get_state(tg_id)
    try:
        if st.get("renew"):
            sid, pid = st["renew"]
            svc = user.services.filter(pk=sid).first()
            plan = Plan.objects.filter(pk=pid, is_active=True).first()
            if not svc or not plan:
                clear_state(tg_id)
                return render(bot, chat_id, sc.services(user), msg)
            order = renew(user, svc, plan)
        else:
            plan = Plan.objects.filter(pk=st.get("plan"), is_active=True).first()
            if not plan:
                clear_state(tg_id)
                return render(bot, chat_id, sc.store(user), msg)
            order = buy_new(user, plan, account_name=st.get("name"), custom_gb=st.get("gb"))
    except OrderError as exc:
        if not st.get("renew"):
            # e.g. the account name is taken: ask for another one
            set_state(tg_id, awaiting="name")
            return bot.send_message(chat_id, tr(user, "bad_name", err=html.escape(str(exc))))
        clear_state(tg_id)
        return bot.send_message(chat_id, tr(user, "bad_name", err=html.escape(str(exc))).split("\n")[0],
                                reply_markup=sc.main_menu(user).markup)
    clear_state(tg_id)
    render(bot, chat_id, sc.invoice(user, order, reused=getattr(order, "reused", False)), msg)


def _after_draft(bot, chat_id, user, tg_id, msg=None) -> None:
    if _needs_terms(user):
        set_state(tg_id, awaiting=None)
        return render(bot, chat_id, sc.terms(user), msg)
    _place_order(bot, chat_id, user, tg_id, msg)


# --- handlers -------------------------------------------------------
def _register(bot: telebot.TeleBot):

    @bot.message_handler(commands=["start"])
    def start(msg):
        close_old_connections()
        user, created, password = _user(msg.from_user)
        payload = (msg.text or "").split(maxsplit=1)[1] if len((msg.text or "").split()) > 1 else ""
        if created and payload:
            _apply_referral(user, payload)
        clear_state(msg.from_user.id)
        text = tr(user, "welcome", site=html.escape(SiteConfig.load().site_name_fa))
        if created:
            text += tr(user, "welcome_new", u=user.username, p=password)
        bot.send_message(msg.chat.id, text)
        if _enforce_gate(bot, msg.chat.id, user, msg.from_user.id):
            render(bot, msg.chat.id, sc.main_menu(user))

    @bot.message_handler(content_types=["photo", "document"])
    def receipt_photo(msg):
        close_old_connections()
        user, *_ = _user(msg.from_user)
        if not _phone_gate(bot, msg.chat.id, user):
            return
        order = sc.open_order(user) or order_awaiting_receipt(user)
        if not order:
            bot.send_message(msg.chat.id, tr(user, "no_open_order"), reply_markup=sc.main_menu(user).markup)
            return
        # a compressed photo, or a document sent as an image file
        if getattr(msg, "photo", None):
            file_id = msg.photo[-1].file_id
        elif getattr(msg, "document", None) and (msg.document.mime_type or "").startswith("image/"):
            file_id = msg.document.file_id
        else:
            bot.send_message(msg.chat.id, tr(user, "receipt_not_image"))
            return
        try:
            file_info = bot.get_file(file_id)
            image_bytes = bot.download_file(file_info.file_path)
            payment = submit_bot_receipt(user, order, image_bytes)
            log.info("bot receipt: payment %s for order %s (%s bytes)",
                     payment.id, order.id, len(image_bytes or b""))
        except Exception as exc:  # noqa: BLE001
            log.exception("bot receipt upload failed for order %s: %s", order.id, exc)
            bot.send_message(msg.chat.id, tr(user, "receipt_fail", err=html.escape(str(exc))))
            return
        order.refresh_from_db()
        bot.send_message(msg.chat.id, tr(user, "receipt_ok"), reply_markup=sc.order_status(user, order).markup)

    @bot.message_handler(content_types=["contact"])
    def contact(msg):
        close_old_connections()
        user, *_ = _user(msg.from_user)
        if not msg.contact or msg.contact.user_id != msg.from_user.id:
            # a forwarded / someone else's contact card — only your own number counts
            _ask_phone(bot, msg.chat.id, user, MSG_NOT_OWN)
            return
        res = link_telegram_phone(user, msg.contact.phone_number)
        if res.status in ("not_iranian", "invalid"):
            _ask_phone(bot, msg.chat.id, user, MSG_NOT_IRANIAN)
            return
        if res.status == "conflict":
            bot.send_message(msg.chat.id, _t(user, *MSG_CONFLICT), reply_markup=types.ReplyKeyboardRemove())
            return
        user = res.user
        done = MSG_MERGED if res.status == "merged" else MSG_PHONE_SAVED
        bot.send_message(msg.chat.id, _t(user, *done), reply_markup=types.ReplyKeyboardRemove())
        if _enforce_gate(bot, msg.chat.id, user, msg.from_user.id):
            render(bot, msg.chat.id, sc.main_menu(user))

    @bot.callback_query_handler(func=lambda c: True)
    def on_cb(c):
        close_old_connections()
        try:
            bot.answer_callback_query(c.id)      # stop the client spinner right away
        except Exception:  # noqa: BLE001
            pass
        user, *_ = _user(c.from_user)
        data = c.data or ""
        chat_id, msg, tg = c.message.chat.id, c.message, c.from_user.id
        try:
            if data == "noop":
                return
            if data in ("m:home", "g:re"):
                clear_state(tg)
                if _enforce_gate(bot, chat_id, user, tg, msg):
                    render(bot, chat_id, sc.main_menu(user), msg)
                return
            if not check_access(user, tg).ok:
                _enforce_gate(bot, chat_id, user, tg, msg)
                return
            _route(bot, chat_id, msg, user, tg, data)
        except Exception as exc:  # noqa: BLE001 - one bad update must not kill the bot
            log.exception("callback %s failed: %s", data, exc)
            bot.send_message(chat_id, tr(user, "error"), reply_markup=sc.main_menu(user).markup)

    # Registered last so the specific handlers above win. Any other message —
    # text, commands, stickers, voice… — lands here: users without a phone
    # (force_share_phone) are asked for it first; typed input continues the
    # current step; everyone else gets the menu.
    @bot.message_handler(func=lambda m: True, content_types=[
        "text", "sticker", "voice", "audio", "video", "video_note", "location", "venue", "animation", "poll", "dice",
    ])
    def fallback(msg):
        close_old_connections()
        user, *_ = _user(msg.from_user)
        if not _enforce_gate(bot, msg.chat.id, user, msg.from_user.id):
            return
        awaiting = get_state(msg.from_user.id).get("awaiting")
        if msg.content_type == "text" and awaiting and not (msg.text or "").startswith("/"):
            _typed(bot, msg, user, awaiting)
            return
        clear_state(msg.from_user.id)
        render(bot, msg.chat.id, sc.main_menu(user))


def _route(bot, chat_id, msg, user, tg, data: str) -> None:
    parts = data.split(":")
    head = parts[0]
    if head == "m":
        action = parts[1] if len(parts) > 1 else "home"
        page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        clear_state(tg)
        if action == "buy":
            return render(bot, chat_id, sc.store(user), msg)
        if action == "svcs":
            return render(bot, chat_id, sc.services(user, page), msg)
        if action == "history":
            return render(bot, chat_id, sc.history(user, page), msg)
        if action == "acc":
            return render(bot, chat_id, sc.account(user), msg)
        if action == "rules":
            return render(bot, chat_id, sc.rules(user), msg)
        if action == "guide":
            return render(bot, chat_id, sc.guide(user), msg)
        if action == "help":
            return render(bot, chat_id, sc.support(user), msg)
        if action == "lang":
            user.language = "en" if user.language != "en" else "fa"
            user.save(update_fields=["language", "updated_at"])
            return render(bot, chat_id, sc.account(user), msg)
        if action == "pwd":
            set_state(tg, awaiting="pwd")
            return render(bot, chat_id, sc.Screen(tr(user, "ask_pwd"), sc._kb([sc._nav(user, "m:acc")])), msg)
        return render(bot, chat_id, sc.main_menu(user), msg)
    if head == "c":
        return render(bot, chat_id, sc.category(user, int(parts[1])), msg)
    if head == "p":
        plan = Plan.objects.filter(pk=int(parts[1]), is_active=True).first()
        return render(bot, chat_id, sc.plan_detail(user, plan) if plan else sc.store(user), msg)
    if head == "pb":
        plan = Plan.objects.filter(pk=int(parts[1]), is_active=True).first()
        if not plan:
            return render(bot, chat_id, sc.store(user), msg)
        clear_state(tg)
        if plan.type == PlanType.CUSTOM_VOLUME:
            set_state(tg, plan=plan.id, awaiting="gb")
            text = tr(user, "ask_gb", lo=plan.min_gb or 1, hi=plan.max_gb or "∞")
        else:
            set_state(tg, plan=plan.id, awaiting="name")
            text = tr(user, "ask_name")
        return render(bot, chat_id, sc.Screen(text, sc._kb([sc._nav(user, f"p:{plan.id}")])), msg)
    if head == "t" and parts[1:] == ["ok"]:
        user.terms_accepted_at = timezone.now()
        user.save(update_fields=["terms_accepted_at", "updated_at"])
        st = get_state(tg)
        if st.get("renew") or (st.get("plan") and st.get("name")):
            return _place_order(bot, chat_id, user, tg, msg)
        return render(bot, chat_id, sc.store(user), msg)
    if head == "o":
        order = Order.objects.filter(pk=int(parts[1]), user=user).select_related("plan", "payment").first()
        if not order:
            return render(bot, chat_id, sc.history(user), msg)
        if len(parts) > 2 or order.status != "pending_payment":
            return render(bot, chat_id, sc.order_status(user, order), msg)
        return render(bot, chat_id, sc.invoice(user, order), msg)
    if head == "rn":
        set_state(tg, renew=[int(parts[1]), int(parts[2])], awaiting=None)
        return _after_draft(bot, chat_id, user, tg, msg)
    if head == "ga":
        return render(bot, chat_id, sc.guide_os(user, parts[1]), msg)
    if head == "s":
        svc = user.services.filter(pk=int(parts[1])).first()
        if not svc:
            return render(bot, chat_id, sc.services(user), msg)
        action = ":".join(parts[2:])
        if action in ("link",):
            return render(bot, chat_id, sc.service_link(user, svc), msg)
        if action == "qr":
            if not svc.subscription_url:
                return render(bot, chat_id, sc.service_link(user, svc), msg)
            return render(bot, chat_id, sc.service_qr(user, svc), msg)
        if action == "revoke":
            return render(bot, chat_id, sc.revoke_confirm(user, svc), msg)
        if action == "revoke:yes":
            try:
                svc = revoke_subscription(svc.id)
            except PanelError as exc:
                return bot.send_message(chat_id, tr(user, "revoke_fail", err=html.escape(str(exc))))
            return render(bot, chat_id, sc.service_qr(user, svc, title=tr(user, "revoked")), msg)
        if action == "rn":
            return render(bot, chat_id, sc.renew_plans(user, svc), msg)
        return render(bot, chat_id, sc.service_detail(user, svc), msg)
    render(bot, chat_id, sc.main_menu(user), msg)


def _typed(bot, msg, user, awaiting: str) -> None:
    """Typed input for the step the user is on."""
    tg, chat_id, text = msg.from_user.id, msg.chat.id, (msg.text or "").strip()
    st = get_state(tg)
    if awaiting == "gb":
        plan = Plan.objects.filter(pk=st.get("plan"), is_active=True).first()
        if not plan:
            clear_state(tg)
            return render(bot, chat_id, sc.store(user))
        lo, hi = plan.min_gb or 1, plan.max_gb or 0
        digits = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
        if not digits.isdigit() or int(digits) < lo or (hi and int(digits) > hi):
            return bot.send_message(chat_id, tr(user, "bad_gb", lo=lo, hi=hi or "∞"))
        set_state(tg, gb=int(digits), awaiting="name")
        return bot.send_message(chat_id, tr(user, "ask_name"))
    if awaiting == "name":
        if not text:
            return bot.send_message(chat_id, tr(user, "ask_name"))
        set_state(tg, name=text[:64], awaiting=None)
        return _after_draft(bot, chat_id, user, tg)
    if awaiting == "pwd":
        try:
            change_password_via_bot(user, text)
        except ValidationError as exc:
            return bot.send_message(chat_id, tr(user, "pwd_bad", err=html.escape("؛ ".join(exc.messages))))
        finally:
            try:
                bot.delete_message(chat_id, msg.message_id)   # never leave the password in the chat
            except Exception:  # noqa: BLE001
                pass
        clear_state(tg)
        return bot.send_message(chat_id, tr(user, "pwd_ok"), reply_markup=sc.account(user).markup)
    clear_state(tg)
    render(bot, chat_id, sc.main_menu(user))


def bot_settings_summary() -> dict:   # used by tests / ops to see what the bot links to
    return {"miniapp_url": sc.miniapp_url(), "site": sc.site_url(), "bot": sc.BOT_USERNAME["value"],
            "public_base": getattr(settings, "PUBLIC_BASE_URL", "")}
