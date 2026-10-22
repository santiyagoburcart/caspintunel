"""Tickets in the sales bot (same rules as the site: everything goes through
`services`). Screens are pure functions returning `screens.Screen`; the router
functions are called by `telegram.bot.sales_bot`.

callback_data:
  customer  tk:home  tk:new  tk:nt:<topic>  tk:list:<page>  tk:v:<id>  tk:r:<id>  tk:c:<id>  tk:o:<id>
  staff     st:l:<o|m>:<page>  st:v:<id>  st:r:<id>  st:a:<id>  st:c:<id>  st:o:<id>
typed steps (cache state): tk_subject → tk_body · tk_reply · st_reply (text or photo / PDF)
Staff screens are Persian (staff accounts have no language setting).
"""
from __future__ import annotations

import html
import logging

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.common.jalali import to_jalali_str

from . import rules, services
from .models import Ticket, TicketStatus

log = logging.getLogger("caspintunel")
PAGE = 6
LAST_MESSAGES = 8
MAX_TEXT = 4000

T = {
    "home": ("🎫 <b>پشتیبانی و تیکت‌ها</b>\nسؤال یا مشکلی دارید؟ یک تیکت باز کنید؛ پاسخ پشتیبانی همین‌جا و در سایت به شما می‌رسد.",
             "🎫 <b>Support tickets</b>\nA question or a problem? Open a ticket — the answer arrives here and on the website."),
    "btn_new": ("➕ تیکت جدید", "➕ New ticket"),
    "btn_list": ("📋 تیکت‌های من", "📋 My tickets"),
    "btn_reply": ("✍️ پاسخ", "✍️ Reply"),
    "btn_view": ("👁 مشاهده", "👁 Open"),
    "btn_close": ("✅ بستن تیکت", "✅ Close ticket"),
    "btn_reopen": ("🔄 بازگشایی", "🔄 Reopen"),
    "btn_tickets": ("🎫 پشتیبانی / تیکت‌ها", "🎫 Support / tickets"),
    "pick_topic": ("موضوع تیکت را انتخاب کنید:", "Pick a topic:"),
    "no_topics": ("فعلاً موضوعی برای تیکت فعال نیست.", "No ticket topics are available right now."),
    "expired_hint": ("⚠️ سرویس شما منقضی شده — برای تمدید از «📦 سرویس‌های من» اقدام کنید. (می‌توانید تیکت را هم ثبت کنید.)",
                     "⚠️ Your service has expired — renew it from “📦 My services”. (You can still open a ticket.)"),
    "ask_subject": ("📝 موضوع: <b>{topic}</b>\nعنوان کوتاه تیکت را بنویسید:", "📝 Topic: <b>{topic}</b>\nType a short subject:"),
    "ask_body": ("✉️ حالا پیام خود را بنویسید (می‌توانید عکس یا PDF هم بفرستید):",
                 "✉️ Now type your message (you can also send a photo or a PDF):"),
    "ask_reply": ("✍️ پاسخ خود به تیکت <b>#{n}</b> را بنویسید یا عکس / PDF بفرستید:",
                  "✍️ Type your reply to ticket <b>#{n}</b> or send a photo / PDF:"),
    "created": ("✅ تیکت <b>#{n}</b> ثبت شد. پاسخ پشتیبانی را همین‌جا دریافت می‌کنید.",
                "✅ Ticket <b>#{n}</b> was opened. You will get the answer here."),
    "sent": ("✅ پیام شما ارسال شد.", "✅ Your message was sent."),
    "list_title": ("📋 <b>تیکت‌های شما</b> ({n})", "📋 <b>Your tickets</b> ({n})"),
    "list_empty": ("هنوز تیکتی ندارید.", "You have no tickets yet."),
    "topic": ("موضوع", "Topic"),
    "status": ("وضعیت", "Status"),
    "you": ("👤 شما", "👤 You"),
    "support": ("🎧 پشتیبانی", "🎧 Support"),
    "reply_alert": ("💬 <b>پاسخ جدید به تیکت #{n}</b>\n{subject}\n\n{body}", "💬 <b>New reply to ticket #{n}</b>\n{subject}\n\n{body}"),
    "older": ("… {n} پیام قبلی در سایت", "… {n} earlier messages on the website"),
    "attach": ("📎 {n} پیوست", "📎 {n} attachment(s)"),
    "err_needs_service": ("این موضوع برای مشتریان است — قبل از اولین خرید از «سوالات قبل از خرید» استفاده کنید.",
                          "This topic is for customers — before your first purchase use “Pre-purchase questions”."),
    "err_too_many_open": ("تعداد تیکت‌های باز شما به حداکثر رسیده — منتظر پاسخ بمانید یا یکی را ببندید.",
                          "You have too many open tickets — wait for an answer or close one."),
    "err_closed": ("این تیکت بسته است — اول آن را بازگشایی کنید.", "This ticket is closed — reopen it first."),
    "err_reopen_expired": ("مهلت بازگشایی این تیکت تمام شده — یک تیکت جدید باز کنید.",
                           "This ticket can no longer be reopened — open a new one."),
    "err_empty": ("پیام خالی است.", "The message is empty."),
    "err_attachment": ("فایل پذیرفته نشد: فقط عکس (JPG/PNG/GIF/WebP) یا PDF تا 5 مگابایت.",
                       "File refused: only images (JPG/PNG/GIF/WebP) or PDF up to 5 MB."),
    "err": ("⚠️ انجام نشد: {e}", "⚠️ Not done: {e}"),
}
STATUS = {
    "open": ("🆕", "باز", "Open"),
    "awaiting_admin": ("⏳", "در انتظار پشتیبانی", "Waiting for support"),
    "awaiting_user": ("💬", "پاسخ داده شد", "Answered"),
    "on_hold": ("⏸", "در حال پیگیری", "On hold"),
    "closed": ("✅", "بسته", "Closed"),
}
PRIORITY = {"low": "کم", "normal": "عادی", "high": "زیاد", "urgent": "فوری"}


def _is_en(user) -> bool:
    return getattr(user, "language", "fa") == "en"


def t(user, key, **fmt) -> str:
    fa, en = T[key]
    s = en if _is_en(user) else fa
    return s.format(**fmt) if fmt else s


def _status(user, status) -> str:
    icon, fa, en = STATUS.get(status, ("•", status, status))
    return f"{icon} {en if user is not None and _is_en(user) else fa}"


def _topic_name(user, topic) -> str:
    return topic.name_en if _is_en(user) else topic.name_fa


def _time(dt) -> str:
    return to_jalali_str(dt, "%Y/%m/%d %H:%M") if dt else ""


def _clip(text: str) -> str:
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT - 2] + "…"


def error_text(user, exc) -> str:
    code = getattr(exc, "code", "attachment" if isinstance(exc, rules.AttachmentError) else "")
    key = f"err_{code}"
    return t(user, key) if key in T else t(user, "err", e=html.escape(str(exc)))


# ================================ customer ====================================
def _sc():
    from apps.telegram.bot import screens as sc

    return sc


def home(user):
    sc = _sc()
    return sc.Screen(t(user, "home"), sc._kb([
        [sc._b(t(user, "btn_new"), "tk:new"), sc._b(t(user, "btn_list"), "tk:list:0")],
        sc._nav(user),
    ]))


def new_topics(user):
    sc = _sc()
    topics = list(rules.topics_for_user(user))
    if not topics:
        return sc.Screen(t(user, "no_topics"), sc._kb([sc._nav(user, "tk:home")]))
    text = t(user, "pick_topic")
    if rules.renew_hint(user) is not None:
        text = t(user, "expired_hint") + "\n\n" + text
    rows = [[sc._b(_topic_name(user, tp), f"tk:nt:{tp.id}")] for tp in topics]
    return sc.Screen(text, sc._kb(rows + [sc._nav(user, "tk:home")]))


def my_list(user, page: int = 0):
    sc = _sc()
    qs = Ticket.objects.filter(user=user).select_related("topic").order_by("-last_activity_at")
    total = qs.count()
    if not total:
        return sc.Screen(t(user, "list_empty"), sc._kb([[sc._b(t(user, "btn_new"), "tk:new")], sc._nav(user, "tk:home")]))
    pages = (total + PAGE - 1) // PAGE
    page = max(0, min(page, pages - 1))
    rows = []
    for tk in qs[page * PAGE:(page + 1) * PAGE]:
        unread = tk.messages.filter(author_staff__isnull=False, is_internal=False, read_by_user_at__isnull=True).exists()
        icon = STATUS.get(tk.status, ("•",))[0]
        rows.append([sc._b(f"{icon} #{tk.number} {'🔴 ' if unread else ''}{tk.subject[:28]}", f"tk:v:{tk.id}")])
    rows.append(sc._pager(user, "tk:list", page, pages))
    rows.append([sc._b(t(user, "btn_new"), "tk:new")])
    rows.append(sc._nav(user, "tk:home"))
    return sc.Screen(t(user, "list_title", n=total), sc._kb(rows))


def _messages_text(viewer_user, ticket, *, staff_view=False) -> str:
    qs = ticket.messages.select_related("author_staff").prefetch_related("attachments")
    if not staff_view:
        qs = qs.filter(is_internal=False)
    msgs = list(qs)
    shown = msgs[-LAST_MESSAGES:]
    show_names = staff_view or rules.bool_setting("tickets_show_staff_name")
    lines = []
    if len(msgs) > len(shown):
        lines.append(t(viewer_user, "older", n=len(msgs) - len(shown)) if not staff_view
                     else f"… {len(msgs) - len(shown)} پیام قبلی در پنل")
    for m in shown:
        if m.from_staff:
            name = (m.author_staff.display_name or m.author_staff.username) if (show_names and m.author_staff) else None
            who = ("🔒 یادداشت داخلی — " if m.is_internal else "🎧 ") + (name or "پشتیبانی") if staff_view \
                else (f"🎧 {html.escape(name)}" if name else t(viewer_user, "support"))
        else:
            who = f"👤 {html.escape(ticket.user.username)}" if staff_view else t(viewer_user, "you")
        att = m.attachments.count()
        body = html.escape(m.body or "")
        extra = ("\n" + (t(viewer_user, "attach", n=att) if not staff_view else f"📎 {att} پیوست")) if att else ""
        lines.append(f"<b>{who}</b> · <i>{_time(m.created_at)}</i>\n{body}{extra}")
    return "\n\n".join(lines)


def view(user, ticket):
    sc = _sc()
    head = (f"🎫 <b>#{ticket.number}</b> — {html.escape(ticket.subject)}\n"
            f"{t(user, 'topic')}: {html.escape(_topic_name(user, ticket.topic))} · {t(user, 'status')}: {_status(user, ticket.status)}")
    services.mark_read(ticket, by_user=True)
    text = _clip(head + "\n\n" + _messages_text(user, ticket))
    rows = []
    if ticket.is_closed:
        from datetime import timedelta

        from django.utils import timezone

        days = rules.setting("tickets_reopen_days")
        if days and ticket.closed_at and timezone.now() - ticket.closed_at <= timedelta(days=days):
            rows.append([sc._b(t(user, "btn_reopen"), f"tk:o:{ticket.id}")])
    else:
        rows.append([sc._b(t(user, "btn_reply"), f"tk:r:{ticket.id}"), sc._b(t(user, "btn_close"), f"tk:c:{ticket.id}")])
    rows.append(sc._nav(user, "tk:list:0"))
    return sc.Screen(text, sc._kb(rows))


def user_reply_alert(user, ticket, snippet: str):
    """(text, reply_markup dict) for TelegramClient.send_message."""
    text = t(user, "reply_alert", n=ticket.number, subject=html.escape(ticket.subject), body=html.escape(snippet))
    return text, {"inline_keyboard": [[
        {"text": t(user, "btn_reply"), "callback_data": f"tk:r:{ticket.id}"},
        {"text": t(user, "btn_view"), "callback_data": f"tk:v:{ticket.id}"},
    ]]}


def route_user(bot, chat_id, msg, user, tg, parts, *, render, set_state, clear_state):
    """Callback `tk:*` from a customer (gate already passed)."""
    sc = _sc()
    action = parts[1] if len(parts) > 1 else "home"
    arg = parts[2] if len(parts) > 2 else ""
    if action == "home":
        clear_state(tg)
        return render(bot, chat_id, home(user), msg)
    if action == "new":
        clear_state(tg)
        return render(bot, chat_id, new_topics(user), msg)
    if action == "nt":
        topic = rules.topics_for_user(user).filter(pk=int(arg or 0)).first()
        if topic is None:
            return render(bot, chat_id, new_topics(user), msg)
        set_state(tg, awaiting="tk_subject", tk_topic=topic.id)
        return render(bot, chat_id, sc.Screen(t(user, "ask_subject", topic=html.escape(_topic_name(user, topic))),
                                              sc._kb([sc._nav(user, "tk:new")])), msg)
    if action == "list":
        clear_state(tg)
        return render(bot, chat_id, my_list(user, int(arg) if arg.isdigit() else 0), msg)
    ticket = Ticket.objects.filter(pk=int(arg) if arg.isdigit() else 0, user=user).select_related("topic").first()
    if ticket is None:
        return render(bot, chat_id, my_list(user), msg)
    if action == "r":
        set_state(tg, awaiting="tk_reply", tk_ticket=ticket.id)
        return render(bot, chat_id, sc.Screen(t(user, "ask_reply", n=ticket.number),
                                              sc._kb([sc._nav(user, f"tk:v:{ticket.id}")])), msg)
    try:
        if action == "c":
            ticket = services.user_close(ticket, user)
        elif action == "o":
            ticket = services.user_reopen(ticket, user)
    except services.TicketError as exc:
        return bot.send_message(chat_id, error_text(user, exc))
    clear_state(tg)
    return render(bot, chat_id, view(user, ticket), msg)


def handle_user_input(bot, chat_id, user, tg, st, *, text="", file=None, render, set_state, clear_state) -> None:
    """Typed text (or a photo / PDF) for the customer's current ticket step."""
    sc = _sc()
    awaiting = st.get("awaiting")
    files = [file] if file is not None else []
    if awaiting == "tk_subject":
        if not text:
            return bot.send_message(chat_id, t(user, "ask_subject", topic="…"))
        set_state(tg, awaiting="tk_body", tk_subject=text[:150])
        return bot.send_message(chat_id, t(user, "ask_body"))
    try:
        if awaiting == "tk_body":
            ticket = services.open_ticket(user, topic_id=st.get("tk_topic"), subject=st.get("tk_subject") or text[:150],
                                          body=text, files=files, channel="bot")
            clear_state(tg)
            bot.send_message(chat_id, t(user, "created", n=ticket.number))
            return render(bot, chat_id, view(user, ticket))
        if awaiting == "tk_reply":
            ticket = Ticket.objects.filter(pk=st.get("tk_ticket"), user=user).first()
            if ticket is None:
                clear_state(tg)
                return render(bot, chat_id, my_list(user))
            services.user_reply(ticket, user, body=text, files=files, channel="bot")
            clear_state(tg)
            bot.send_message(chat_id, t(user, "sent"))
            ticket.refresh_from_db()
            return render(bot, chat_id, view(user, ticket))
    except (services.TicketError, rules.AttachmentError) as exc:
        if getattr(exc, "code", "") in ("needs_service", "too_many_open", "closed", "reopen_expired"):
            clear_state(tg)
        return bot.send_message(chat_id, error_text(user, exc))
    clear_state(tg)
    return render(bot, chat_id, sc.main_menu(user))


# ================================= staff ======================================
def staff_for(tg_id):
    """The linked, active staff member allowed to see tickets — else None."""
    from apps.accounts.models import Staff

    s = Staff.objects.filter(telegram_id=tg_id, is_active=True).select_related("role").first()
    if s is None or not (s.is_superadmin or s.has_perm("tickets.view")):
        return None
    return s


def _kb(rows):
    from telebot import types

    kb = types.InlineKeyboardMarkup()
    for row in rows:
        if row:
            kb.row(*[types.InlineKeyboardButton(text, callback_data=data) for text, data in row])
    return kb


def staff_list(staff, flt: str = "o", page: int = 0):
    sc = _sc()
    qs = rules.staff_queryset(staff).exclude(status=TicketStatus.CLOSED).select_related("user", "topic")
    if flt == "m":
        qs = qs.filter(assigned_to=staff)
    qs = qs.order_by("-last_activity_at")
    total = qs.count()
    pages = max(1, (total + PAGE - 1) // PAGE)
    page = max(0, min(page, pages - 1))
    rows = [[("📂 باز" + (" ✓" if flt == "o" else ""), "st:l:o:0"), ("🙋 مال من" + (" ✓" if flt == "m" else ""), "st:l:m:0")]]
    for tk in qs[page * PAGE:(page + 1) * PAGE]:
        icon = STATUS.get(tk.status, ("•",))[0]
        mine = "🙋 " if tk.assigned_to_id == staff.id else ("" if tk.assigned_to_id else "🆓 ")
        rows.append([(f"{icon} #{tk.number} {mine}{tk.subject[:26]}", f"st:v:{tk.id}")])
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(("« قبلی", f"st:l:{flt}:{page - 1}"))
        nav.append((f"{page + 1}/{pages}", "noop"))
        if page < pages - 1:
            nav.append(("بعدی »", f"st:l:{flt}:{page + 1}"))
        rows.append(nav)
    title = "📥 <b>تیکت‌ها</b> — " + ("باز" if flt == "o" else "سپرده‌شده به من") + f" ({total})"
    if not total:
        title += "\n\nتیکتی نیست."
    return sc.Screen(title, _kb(rows))


def staff_view(staff, ticket):
    sc = _sc()
    a = ticket.assigned_to
    head = (f"🎫 <b>#{ticket.number}</b> — {html.escape(ticket.subject)}\n"
            f"👤 {html.escape(ticket.user.username)} · {html.escape(ticket.topic.name_fa)}\n"
            f"وضعیت: {_status(None, ticket.status)} · اولویت: {PRIORITY.get(ticket.priority, ticket.priority)}\n"
            f"مسئول: {html.escape(a.username) if a else '—'}")
    services.mark_read(ticket, by_user=False)
    text = _clip(head + "\n\n" + _messages_text(None, ticket, staff_view=True))
    rows, first = [], []
    if staff.has_perm("tickets.reply"):
        first.append(("✍️ پاسخ", f"st:r:{ticket.id}"))
    if staff.has_perm("tickets.assign") and ticket.assigned_to_id != staff.id:
        first.append(("🙋 به من بسپار", f"st:a:{ticket.id}"))
    if first:
        rows.append(first)
    if staff.has_perm("tickets.close"):
        rows.append([("🔄 بازگشایی", f"st:o:{ticket.id}")] if ticket.is_closed else [("✅ بستن", f"st:c:{ticket.id}")])
    rows.append([("⬅️ تیکت‌ها", "st:l:o:0")])
    return sc.Screen(text, _kb(rows))


def staff_alert_markup(staff, ticket) -> dict:
    row = [{"text": "✍️ پاسخ", "callback_data": f"st:r:{ticket.id}"},
           {"text": "👁 مشاهده", "callback_data": f"st:v:{ticket.id}"}]
    rows = [row]
    second = []
    if ticket.assigned_to_id is None and (staff.is_superadmin or staff.has_perm("tickets.assign")):
        second.append({"text": "🙋 به من بسپار", "callback_data": f"st:a:{ticket.id}"})
    if staff.is_superadmin or staff.has_perm("tickets.close"):
        second.append({"text": "✅ بستن", "callback_data": f"st:c:{ticket.id}"})
    if second:
        rows.append(second)
    return {"inline_keyboard": rows}


def route_staff(bot, chat_id, msg, staff, tg, parts, *, render, set_state, clear_state):
    """Callback `st:*` from a linked staff member (no customer gate, no customer account)."""
    from telebot import types

    action = parts[1] if len(parts) > 1 else "l"
    if action == "l":
        flt = parts[2] if len(parts) > 2 and parts[2] in ("o", "m") else "o"
        page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
        clear_state(tg)
        return render(bot, chat_id, staff_list(staff, flt, page), msg)
    arg = parts[2] if len(parts) > 2 else ""
    ticket = rules.staff_queryset(staff).select_related("user", "topic", "assigned_to") \
        .filter(pk=int(arg) if arg.isdigit() else 0).first()
    if ticket is None:
        return render(bot, chat_id, staff_list(staff), msg)
    try:
        if action == "r":
            if not staff.has_perm("tickets.reply"):
                return bot.send_message(chat_id, "⛔️ دسترسی پاسخ ندارید.")
            set_state(tg, awaiting="st_reply", st_ticket=ticket.id)
            return bot.send_message(chat_id, f"✍️ پاسخ به تیکت <b>#{ticket.number}</b> را بنویسید یا عکس / PDF بفرستید:",
                                    reply_markup=types.ForceReply(selective=True))
        if action == "a":
            if not staff.has_perm("tickets.assign"):
                return bot.send_message(chat_id, "⛔️ دسترسی سپردن ندارید.")
            services.assign(ticket, staff, staff)
        elif action in ("c", "o"):
            if not staff.has_perm("tickets.close"):
                return bot.send_message(chat_id, "⛔️ دسترسی بستن / بازگشایی ندارید.")
            services.set_status(ticket, staff, TicketStatus.CLOSED if action == "c" else TicketStatus.AWAITING_ADMIN)
    except services.TicketError as exc:
        return bot.send_message(chat_id, f"⚠️ انجام نشد: {html.escape(str(exc))}")
    ticket.refresh_from_db()
    return render(bot, chat_id, staff_view(staff, ticket), msg)


def handle_staff_input(bot, chat_id, staff, tg, st, *, text="", file=None, render, clear_state) -> None:
    ticket = rules.staff_queryset(staff).filter(pk=st.get("st_ticket")).first()
    clear_state(tg)
    if ticket is None or not staff.has_perm("tickets.reply"):
        return render(bot, chat_id, staff_list(staff))
    try:
        services.staff_reply(ticket, staff, body=text, files=[file] if file is not None else [], channel="bot")
    except (services.TicketError, rules.AttachmentError) as exc:
        return bot.send_message(chat_id, f"⚠️ ارسال نشد: {html.escape(str(exc))}")
    bot.send_message(chat_id, f"✅ پاسخ تیکت #{ticket.number} ارسال شد.")
    ticket.refresh_from_db()
    return render(bot, chat_id, staff_view(staff, ticket))


def upload_from_bot(data: bytes, name: str, mime: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(name or "file", data, content_type=mime or "application/octet-stream")
