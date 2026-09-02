"""
Sales bot wiring (pyTelegramBotAPI, synchronous — pairs naturally with the
Django ORM). Conversation logic lives in apps.telegram.{accounts,gate,shop};
this module only maps Telegram updates onto it.

Not unit-tested (needs Telegram); the logic it calls is covered by tests.
"""
from __future__ import annotations

import io
import logging

import qrcode
import telebot
from django.conf import settings
from django.db import close_old_connections
from telebot import types

from apps.orders.models import Order
from apps.panel.models import Service
from apps.plans.models import Plan, PlanType
from apps.settings_app.models import SiteConfig

from ..accounts import ensure_bot_user, link_phone
from ..config import get_bot_config
from ..gate import check_access
from ..models import BotType
from ..shop import (
    active_plans,
    buy_new,
    delivery_message,
    order_awaiting_receipt,
    payment_instructions,
    plan_label,
    renew,
    service_summary,
    submit_bot_receipt,
    user_services,
)
from . import keyboards as kb

log = logging.getLogger("caspintunel")


def build_bot() -> telebot.TeleBot | None:
    cfg = get_bot_config(BotType.SALES)
    if not cfg or not cfg.is_active or not cfg.token:
        return None
    if cfg.proxy_url:
        telebot.apihelper.proxy = {"http": cfg.proxy_url, "https": cfg.proxy_url}
    bot = telebot.TeleBot(cfg.token, parse_mode="HTML", threaded=False)
    _register(bot)
    _sync_menu_button(bot)
    return bot


def _sync_menu_button(bot: telebot.TeleBot) -> None:
    """Point the bot's menu button at the Mini App (our user SPA). Idempotent;
    a Telegram hiccup here must not stop the bot."""
    url = getattr(settings, "MINIAPP_URL", "") or ""
    if not url.startswith("https://"):
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


def _welcome_text(created, password, username):
    site = SiteConfig.load().site_name_fa
    text = f"به ربات <b>{site}</b> خوش آمدید."
    if created:
        text += (
            "\n\nیک حساب سایت برای شما ساخته شد:\n"
            f"نام کاربری: <code>{username}</code>\nرمز عبور: <code>{password}</code>\n"
            "می‌توانید با همین مشخصات وارد سایت شوید."
        )
    return text


def _enforce_gate(bot, chat_id, user, tg_id) -> bool:
    result = check_access(user, tg_id)
    if result.ok:
        return True
    if result.missing_channels:
        bot.send_message(chat_id, "برای استفاده از ربات ابتدا در کانال‌های زیر عضو شوید:",
                         reply_markup=kb.join_channels(result.missing_channels))
    if result.need_phone:
        bot.send_message(chat_id, "لطفاً شمارهٔ تلفن خود را به اشتراک بگذارید:",
                         reply_markup=kb.share_phone())
    return False


# --- handlers -------------------------------------------------------
def _register(bot: telebot.TeleBot):

    @bot.message_handler(commands=["start"])
    def start(msg):
        close_old_connections()
        user, created, password = _user(msg.from_user)
        bot.send_message(msg.chat.id, _welcome_text(created, password, user.username))
        if _enforce_gate(bot, msg.chat.id, user, msg.from_user.id):
            bot.send_message(msg.chat.id, "یک گزینه را انتخاب کنید:", reply_markup=kb.main_menu())

    @bot.message_handler(content_types=["photo", "document"])
    def receipt_photo(msg):
        close_old_connections()
        user, *_ = _user(msg.from_user)
        order = order_awaiting_receipt(user)
        if not order:
            bot.send_message(msg.chat.id, "سفارشی در انتظار پرداخت ندارید. برای خرید /start را بزنید.")
            return
        # a compressed photo, or a document sent as an image file
        if getattr(msg, "photo", None):
            file_id = msg.photo[-1].file_id
        elif getattr(msg, "document", None) and (msg.document.mime_type or "").startswith("image/"):
            file_id = msg.document.file_id
        else:
            bot.send_message(msg.chat.id, "لطفاً عکس رسید را بفرستید (تصویر، نه فایل دیگر).")
            return
        try:
            file_info = bot.get_file(file_id)
            image_bytes = bot.download_file(file_info.file_path)
            payment = submit_bot_receipt(user, order, image_bytes)
            log.info("bot receipt: payment %s for order %s (%s bytes)",
                     payment.id, order.id, len(image_bytes or b""))
        except Exception as exc:  # noqa: BLE001
            log.exception("bot receipt upload failed for order %s: %s", order.id, exc)
            bot.send_message(msg.chat.id, f"ثبت رسید ناموفق بود: {exc}\nلطفاً دوباره تلاش کنید.")
            return
        bot.send_message(
            msg.chat.id,
            "رسید شما دریافت شد ✅\nدر انتظار تأیید ادمین. پس از تأیید، سرویس فعال می‌شود.",
            reply_markup=kb.order_status(order.id),
        )

    @bot.message_handler(content_types=["contact"])
    def contact(msg):
        close_old_connections()
        if msg.contact and msg.contact.user_id == msg.from_user.id:
            user, *_ = _user(msg.from_user)
            link_phone(user, msg.contact.phone_number)
            bot.send_message(msg.chat.id, "شماره ثبت شد ✅")
            if _enforce_gate(bot, msg.chat.id, user, msg.from_user.id):
                bot.send_message(msg.chat.id, "منو:", reply_markup=kb.main_menu())

    @bot.callback_query_handler(func=lambda c: True)
    def on_cb(c):
        close_old_connections()
        user, *_ = _user(c.from_user)
        data = c.data or ""
        try:
            if data in ("m:home", "g:re"):
                if _enforce_gate(bot, c.message.chat.id, user, c.from_user.id):
                    bot.send_message(c.message.chat.id, "منو:", reply_markup=kb.main_menu())
            elif not check_access(user, c.from_user.id).ok:
                _enforce_gate(bot, c.message.chat.id, user, c.from_user.id)
            elif data == "m:buy":
                bot.send_message(c.message.chat.id, "یک پلن را انتخاب کنید:",
                                 reply_markup=kb.plan_list(active_plans()))
            elif data == "m:svcs":
                _send_services(bot, c.message.chat.id, user)
            elif data == "m:help":
                site = SiteConfig.load()
                bot.send_message(c.message.chat.id,
                                 f"پشتیبانی: {site.support_telegram or 'به‌زودی'}")
            elif data.startswith("p:"):
                _start_purchase(bot, c.message.chat.id, user, int(data.split(":")[1]))
            elif data.startswith("rn:"):
                _, sid, pid = data.split(":")
                _do_renew(bot, c.message.chat.id, user, int(sid), int(pid))
            elif data.startswith("s:") and data.endswith(":qr"):
                _send_qr(bot, c.message.chat.id, user, int(data.split(":")[1]))
            elif data.startswith("s:") and data.endswith(":rn"):
                bot.send_message(c.message.chat.id, "پلن تمدید را انتخاب کنید:",
                                 reply_markup=kb.plan_list(active_plans(), svc_id=int(data.split(":")[1])))
            elif data.startswith("s:"):
                _send_service_detail(bot, c.message.chat.id, user, int(data.split(":")[1]))
            elif data.startswith("o:") and data.endswith(":st"):
                _check_order(bot, c.message.chat.id, user, int(data.split(":")[1]))
        except Exception as exc:  # noqa: BLE001 - one bad update must not kill the bot
            log.exception("callback %s failed: %s", data, exc)
            bot.send_message(c.message.chat.id, "خطایی رخ داد، دوباره تلاش کنید.")
        finally:
            try:
                bot.answer_callback_query(c.id)
            except Exception:  # noqa: BLE001
                pass

    def _send_services(bot, chat_id, user):
        services = list(user_services(user))
        if not services:
            bot.send_message(chat_id, "هنوز سرویسی ندارید.", reply_markup=kb.main_menu())
            return
        bot.send_message(chat_id, "سرویس‌های شما:", reply_markup=kb.service_list(services))

    def _send_service_detail(bot, chat_id, user, sid):
        svc = user.services.filter(pk=sid).first()
        if not svc:
            return
        bot.send_message(chat_id, service_summary(svc), reply_markup=kb.service_detail(svc))

    def _send_qr(bot, chat_id, user, sid):
        svc = user.services.filter(pk=sid).first()
        if not svc or not svc.subscription_url:
            return
        buf = io.BytesIO()
        qrcode.make(svc.subscription_url).save(buf, format="PNG")
        bot.send_photo(chat_id, buf.getvalue(), caption=svc.subscription_url)

    def _start_purchase(bot, chat_id, user, plan_id):
        plan = Plan.objects.filter(pk=plan_id, is_active=True).first()
        if not plan:
            return
        if plan.type == PlanType.CUSTOM_VOLUME:
            m = bot.send_message(chat_id, f"چند گیگابایت؟ (بین {plan.min_gb or 1} و {plan.max_gb})")
            bot.register_next_step_handler(m, _got_custom_gb, plan.id)
        else:
            m = bot.send_message(chat_id, "یک نام دلخواه برای اکانت وارد کنید (حروف/اعداد انگلیسی):")
            bot.register_next_step_handler(m, _got_account_name, plan.id)

    def _got_account_name(msg, plan_id):
        close_old_connections()
        user, *_ = _user(msg.from_user)
        plan = Plan.objects.filter(pk=plan_id, is_active=True).first()
        try:
            order = buy_new(user, plan, account_name=(msg.text or "").strip())
        except Exception as exc:  # noqa: BLE001
            bot.send_message(msg.chat.id, f"ثبت نشد: {exc}")
            return
        bot.send_message(msg.chat.id, payment_instructions(order), reply_markup=kb.order_status(order.id))

    def _got_custom_gb(msg, plan_id):
        close_old_connections()
        user, *_ = _user(msg.from_user)
        plan = Plan.objects.filter(pk=plan_id, is_active=True).first()
        try:
            gb = int((msg.text or "").strip())
            order = buy_new(user, plan, account_name=f"cv{user.id}{msg.message_id}", custom_gb=gb)
        except Exception as exc:  # noqa: BLE001
            bot.send_message(msg.chat.id, f"ثبت نشد: {exc}")
            return
        bot.send_message(msg.chat.id, payment_instructions(order), reply_markup=kb.order_status(order.id))

    def _do_renew(bot, chat_id, user, sid, pid):
        svc = user.services.filter(pk=sid).first()
        plan = Plan.objects.filter(pk=pid, is_active=True).first()
        if not svc or not plan:
            return
        try:
            order = renew(user, svc, plan)
        except Exception as exc:  # noqa: BLE001
            bot.send_message(chat_id, f"ثبت نشد: {exc}")
            return
        bot.send_message(chat_id, payment_instructions(order), reply_markup=kb.order_status(order.id))

    def _check_order(bot, chat_id, user, order_id):
        order = (Order.objects.filter(pk=order_id, user=user)
                 .select_related("service", "payment").first())
        if not order:
            return
        status_fa = {
            "pending_payment": "در انتظار پرداخت", "paid": "پرداخت‌شده، در حال ساخت سرویس",
            "completed": "تکمیل شد", "rejected": "رد شد", "failed": "ناموفق",
            "expired": "مهلت پرداخت تمام شد",
        }.get(order.status, order.status)
        msg = f"وضعیت سفارش: {status_fa}"
        pay = getattr(order, "payment", None)
        if order.status == "pending_payment" and pay:
            if pay.status == "pending":
                msg += "\n📸 رسید شما ثبت شده و در انتظار تأیید ادمین است."
            elif pay.status == "rejected":
                msg += f"\n❌ رسید رد شد: {pay.reject_reason or 'نامشخص'}\nلطفاً عکس رسید جدید ارسال کنید."
        elif order.status == "pending_payment":
            msg += "\nپس از واریز، عکس رسید را همین‌جا ارسال کنید."
        bot.send_message(chat_id, msg)
        if order.status == "completed" and order.service and order.service.subscription_url:
            bot.send_message(chat_id, delivery_message(order.service),
                             reply_markup=kb.service_detail(order.service))
