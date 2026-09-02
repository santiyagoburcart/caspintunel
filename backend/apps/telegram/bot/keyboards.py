"""Inline-keyboard builders for the sales bot."""
from django.conf import settings
from telebot import types

from apps.plans.models import PlanType
from apps.telegram.shop import plan_label

MINIAPP_URL = getattr(settings, "MINIAPP_URL", "") or ""


def main_menu():
    kb = types.InlineKeyboardMarkup()
    if MINIAPP_URL.startswith("https://"):
        kb.add(types.InlineKeyboardButton(
            "🌐 باز کردن اپ", web_app=types.WebAppInfo(url=MINIAPP_URL)))
    kb.add(types.InlineKeyboardButton("🛒 خرید سرویس", callback_data="m:buy"))
    kb.add(types.InlineKeyboardButton("📦 سرویس‌های من", callback_data="m:svcs"))
    kb.add(types.InlineKeyboardButton("☎️ پشتیبانی", callback_data="m:help"))
    return kb


def plan_list(plans, *, prefix="p", svc_id=None):
    kb = types.InlineKeyboardMarkup()
    for plan in plans:
        data = f"{prefix}:{plan.id}" if svc_id is None else f"rn:{svc_id}:{plan.id}"
        kb.add(types.InlineKeyboardButton(plan_label(plan), callback_data=data))
    kb.add(types.InlineKeyboardButton("« بازگشت", callback_data="m:home"))
    return kb


def service_list(services):
    kb = types.InlineKeyboardMarkup()
    for svc in services:
        kb.add(types.InlineKeyboardButton(f"{svc.panel_username} — {svc.status}",
                                          callback_data=f"s:{svc.id}"))
    kb.add(types.InlineKeyboardButton("« بازگشت", callback_data="m:home"))
    return kb


def service_detail(svc):
    kb = types.InlineKeyboardMarkup()
    if svc.subscription_url:
        kb.add(types.InlineKeyboardButton("📱 دریافت QR", callback_data=f"s:{svc.id}:qr"))
    kb.add(types.InlineKeyboardButton("🔄 تمدید", callback_data=f"s:{svc.id}:rn"))
    kb.add(types.InlineKeyboardButton("« سرویس‌ها", callback_data="m:svcs"))
    return kb


def order_status(order_id):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔁 بررسی وضعیت پرداخت", callback_data=f"o:{order_id}:st"))
    kb.add(types.InlineKeyboardButton("« منو", callback_data="m:home"))
    return kb


def join_channels(channels):
    kb = types.InlineKeyboardMarkup()
    for ch in channels:
        ident = ch.channel_id
        url = f"https://t.me/{ident.lstrip('@')}" if not str(ident).startswith("-") else None
        if url:
            kb.add(types.InlineKeyboardButton(f"عضویت در {ch.title or ident}", url=url))
    kb.add(types.InlineKeyboardButton("✅ عضو شدم، بررسی کن", callback_data="g:re"))
    return kb


def share_phone():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(types.KeyboardButton("📞 اشتراک‌گذاری شماره", request_contact=True))
    return kb
