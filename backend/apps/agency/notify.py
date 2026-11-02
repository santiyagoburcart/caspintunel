"""Agency events → staff on Telegram (v1.33) + a browser push and the panel badge.

Before v1.33 `managers._notify_staff` only cleared the badge cache, so nothing ever reached
Telegram. Now every event goes through `apps.common.staff_alert.alert_staff`: a DM from the
sales bot to each active staff member with the permission and a linked Telegram, else the
backup chat (without buttons — that is another bot).

Approval requests (a group manager created an admin / added volume) carry inline buttons
Approve / Reject. The buttons are only a shortcut: `handle_callback` checks the pressing
staff member's permissions exactly like the panel (approve = agency.manage + agency.accounting,
reject = agency.manage, with a confirm step) and calls the same `managers.approve / reject`.

callback_data: ag:a:<id> approve · ag:r:<id> ask to reject · ag:rc:<id> reject (confirmed) ·
ag:x:<id> cancel.
"""
from __future__ import annotations

import logging

from django.core.cache import cache

from apps.common.staff_alert import alert_staff

log = logging.getLogger("caspintunel")

PERM = "agency.manage"


def _gb(v) -> str:
    try:
        return f"{float(v):g}"
    except (TypeError, ValueError):
        return str(v)


def _push(title: str, body: str, route: str, tag: str) -> dict:
    return {"title": title, "body": body, "url": route, "tag": tag}


def approval_buttons(rid: int) -> list:
    return [[{"text": "✅ تأیید · Approve", "callback_data": f"ag:a:{rid}"},
             {"text": "❌ رد · Reject", "callback_data": f"ag:r:{rid}"}]]


def approval_requested(req) -> int:
    from apps.common.links import admin_link

    cache.delete("agency:approvals:badge")
    what_fa = "ساخت ادمین" if req.kind == "create" else "افزایش حجم"
    what_en = "new admin" if req.kind == "create" else "volume added"
    text = (f"🟡 درخواست تأیید نمایندگی #{req.id}: {what_fa}\n"
            f"ادمین {req.admin_username} · +{_gb(req.gb)} GB · گروه {req.group_name} · مدیر {req.manager_username}\n"
            f"Agency approval #{req.id}: {what_en} — {req.admin_username} +{_gb(req.gb)} GB "
            f"(group {req.group_name}, manager {req.manager_username})\n{admin_link('/agency/approvals')}")
    return alert_staff(text, perm=PERM, buttons=approval_buttons(req.id), dedupe_key=f"agency:req:{req.id}",
                       ttl=86400, push=_push(f"درخواست تأیید #{req.id} · Approval #{req.id}",
                                            f"{req.admin_username} +{_gb(req.gb)} GB · {req.manager_username}",
                                            "/agency/approvals", f"agency-req:{req.id}"))


def cap_reached(m, cap_gb, pending_gb) -> int:
    """A group manager hit its unapproved-volume cap: once per manager until the pending total changes."""
    text = (f"⛔️ سقف حجم تأییدنشدهٔ مدیر گروه {m.username} پر شد ({_gb(pending_gb)} از {_gb(cap_gb)} GB) — "
            f"تا تأیید درخواست‌ها حجم تازه نمی‌تواند بدهد.\n"
            f"Group manager {m.username} reached the unapproved cap ({_gb(pending_gb)}/{_gb(cap_gb)} GB).")
    return alert_staff(text, perm=PERM, dedupe_key=f"agency:cap:{m.id}:{pending_gb}", ttl=7 * 86400,
                       push=_push(f"سقف مدیر گروه پر شد · Cap reached", m.username, "/agency/approvals",
                                  f"agency-cap:{m.id}"))


def admin_changed(m, username: str, what: str) -> int:
    """A group manager enabled / disabled an admin or changed its role (password: silent)."""
    fa = {"enabled": "فعال کرد", "disabled": "غیرفعال کرد", "role": "نقش را عوض کرد",
          "password": "رمز را عوض کرد"}.get(what, what)
    en = {"enabled": "enabled", "disabled": "disabled", "role": "changed the role of",
          "password": "changed the password of"}.get(what, what)
    icon = "🔴" if what == "disabled" else "🟢" if what == "enabled" else "ℹ️"
    text = f"{icon} مدیر گروه {m.username} ادمین {username} را {fa}.\nGroup manager {m.username} {en} admin {username}."
    return alert_staff(text, perm=PERM, silent=what in ("password", "role"),
                       push=None if what in ("password", "role") else
                       _push(f"{icon} {username}", f"{m.username}: {en}", f"/agency/admins/{username}",
                             f"agency-admin:{username}"))


# ------------------------------------------------------------------ Telegram buttons
def staff_for_tg(tg_id):
    from apps.accounts.models import Staff

    return Staff.objects.filter(telegram_id=tg_id, is_active=True).select_related("role").first()


def handle_callback(bot, chat_id, message, tg_id, data: str) -> str:
    """Route an `ag:*` button. Returns a short result code (for tests / logs)."""
    from . import managers as M

    parts = (data or "").split(":")
    if len(parts) != 3 or not parts[2].isdigit():
        return "bad"
    act, rid = parts[1], int(parts[2])
    staff = staff_for_tg(tg_id)
    if staff is None:
        bot.send_message(chat_id, "⛔️ این تلگرام به یک ادمین فعال پنل متصل نیست.\nThis Telegram is not linked to an active staff account.")
        return "no_staff"
    if not staff.has_perm(PERM):
        bot.send_message(chat_id, "⛔️ دسترسی agency.manage ندارید.\nYou need agency.manage.")
        return "forbidden"
    original = getattr(message, "text", "") or ""

    def done(line: str):
        try:
            bot.edit_message_text(f"{original}\n\n{line}", chat_id, message.message_id)
        except Exception:  # noqa: BLE001 — old message / same text: just answer below
            bot.send_message(chat_id, line)

    if act == "a":
        if not staff.has_perm("agency.accounting"):
            bot.send_message(chat_id, "⛔️ تأیید یعنی ثبت بدهی — دسترسی agency.accounting لازم است.\n"
                                      "Approving records a charge — you need agency.accounting.")
            return "forbidden"
        try:
            M.approve(rid, staff, may_price=True)
        except M.ManagerError as exc:
            if exc.code == "no_price":
                bot.send_message(chat_id, f"⚠️ برای این ادمین قیمت هر گیگ ثبت نشده — از پنل تأیید کنید.\n{exc}")
            else:
                bot.send_message(chat_id, f"⚠️ {exc}")
            return exc.code
        done(f"✅ تأیید شد توسط {staff.username} · Approved by {staff.username}")
        return "approved"
    if act == "r":
        bot.send_message(chat_id, f"رد درخواست #{rid}؟ حجم روی پاسارگارد پس گرفته می‌شود.\n"
                                  f"Reject request #{rid}? The volume is taken back on PasarGuard.",
                         reply_markup=_confirm_markup(rid))
        return "confirm"
    if act == "rc":
        try:
            M.reject(rid, staff, "rejected from Telegram")
        except M.ManagerError as exc:
            bot.send_message(chat_id, f"⚠️ {exc}")
            return exc.code
        done(f"❌ رد شد توسط {staff.username} · Rejected by {staff.username}")
        return "rejected"
    if act == "x":
        done("لغو شد · Cancelled")
        return "cancelled"
    return "bad"


def _confirm_markup(rid: int):
    from telebot import types

    kb = types.InlineKeyboardMarkup()
    kb.row(types.InlineKeyboardButton("❌ بله، رد شود · Yes, reject", callback_data=f"ag:rc:{rid}"),
           types.InlineKeyboardButton("انصراف · Cancel", callback_data=f"ag:x:{rid}"))
    return kb
