"""Every sales-bot screen as a pure function → `Screen(text, markup, photo)`.

No Telegram I/O here (testable with the DB only); `sales_bot` renders a
screen by editing the current message in place.

callback_data (all ≤ 64 bytes; old buttons still in users' chats keep working):
  tk:* tickets (apps/tickets/bot.py)  st:* staff tickets
  m:home  m:buy  m:svcs[:page]  m:history[:page]  m:acc  m:rules  m:guide  m:help  m:pwd  m:lang
  c:<i> category  p:<plan> plan  pb:<plan> buy  t:ok accept rules
  o:<order> invoice  o:<order>:st status
  s:<svc> detail  s:<svc>:link  s:<svc>:qr  s:<svc>:revoke[:yes]  s:<svc>:rn  rn:<svc>:<plan>
  ga:<os> app guide  g:re gate re-check  noop
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from urllib.parse import quote

from django.conf import settings
from django.utils import timezone
from telebot import types

from apps.common.jalali import to_jalali_str
from apps.orders.models import Order, OrderStatus
from apps.payments_sms.models import BankCard, PaymentStatus
from apps.plans.models import PlanType
from apps.settings_app.models import Page, SiteConfig

from ..shop import active_plans, product_display_mode, qr_png
from .texts import HIST_STATUS, ORDER_STATUS, ORDER_TYPE, OS_APPS, SERVICE_STATUS, is_en, money, pick, tr

GB = 1024 ** 3
PAGE_SIZE = 6
MAX_TEXT = 4000          # Telegram message limit is 4096
BOT_USERNAME = {"value": ""}   # filled by sales_bot at start (get_me)


@dataclass
class Screen:
    text: str
    markup: types.InlineKeyboardMarkup | None = None
    photo: bytes | None = None


def _kb(rows) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    for row in rows:
        if row:
            kb.row(*row)
    return kb


def _b(text, data=None, **kw) -> types.InlineKeyboardButton:
    if data is not None:
        assert len(data.encode()) <= 64, data
        return types.InlineKeyboardButton(text, callback_data=data)
    return types.InlineKeyboardButton(text, **kw)


def _nav(user, back: str | None = None):
    row = []
    if back:
        row.append(_b(tr(user, "btn_back"), back))
    row.append(_b(tr(user, "btn_home"), "m:home"))
    return row


def _clip(text: str) -> str:
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT - 2] + "…"


def miniapp_url() -> str:
    url = getattr(settings, "MINIAPP_URL", "") or getattr(settings, "PUBLIC_BASE_URL", "")
    return url if url.startswith("https://") else ""


def site_url() -> str:
    domain = (SiteConfig.load().site_domain or "").strip().strip("/")
    return f"https://{domain}" if domain else getattr(settings, "PUBLIC_BASE_URL", "").rstrip("/")


# --- shared data ---------------------------------------------------------
def open_order(user):
    """The customer's open order (same rule as the site resume): pending,
    unexpired, without a rejected/approved payment."""
    return (Order.objects.filter(user=user, status=OrderStatus.PENDING_PAYMENT, unique_expire_at__gt=timezone.now())
            .exclude(payment__status__in=[PaymentStatus.REJECTED, PaymentStatus.APPROVED])
            .select_related("plan").order_by("-created_at").first())


def plan_name(user, plan) -> str:
    return pick(user, plan.name_fa, plan.name_en) if plan else "—"


def _category(user, plan) -> str:
    return pick(user, plan.category_fa, plan.category_en).strip()


def categories(user, plans):
    """[(label, [plans])] in first-seen order, uncategorised last."""
    groups, order = {}, []
    for p in plans:
        label = _category(user, p) or tr(user, "other")
        if label not in groups:
            groups[label] = []
            order.append(label)
        groups[label].append(p)
    order.sort(key=lambda lbl: 1 if lbl == tr(user, "other") else 0)
    return [(lbl, groups[lbl]) for lbl in order]


def plan_button_label(user, plan) -> str:
    if plan.type == PlanType.CUSTOM_VOLUME:
        return f"{plan_name(user, plan)} · {tr(user, 'selectable', lo=plan.min_gb or 1, hi=plan.max_gb or '∞')}"
    vol = tr(user, "unlimited") if not plan.data_limit else tr(user, "gb", n=plan.data_limit // GB)
    days = tr(user, "no_expiry") if not plan.duration_days else tr(user, "days", n=plan.duration_days)
    return f"{plan_name(user, plan)} · {vol} · {days} · {money(user, plan.final_price)}"[:64]


# --- main menu -------------------------------------------------------------
def main_menu(user) -> Screen:
    rows = []
    o = open_order(user)
    if o:
        rows.append([_b(tr(user, "btn_open_order", id=o.id), f"o:{o.id}")])
    rows += [
        [_b(tr(user, "btn_buy"), "m:buy"), _b(tr(user, "btn_svcs"), "m:svcs")],
        [_b(tr(user, "btn_history"), "m:history"), _b(tr(user, "btn_acc"), "m:acc")],
        [_b(tr(user, "btn_rules"), "m:rules"), _b(tr(user, "btn_guide"), "m:guide")],
    ]
    rows.append([_b(tr(user, "btn_tickets"), "tk:home")])
    from apps.accounts.models import Staff

    if user.telegram_id and Staff.objects.filter(telegram_id=user.telegram_id, is_active=True).exists():
        rows.append([_b(tr(user, "btn_staff_tickets"), "st:l:o:0")])
    last = [_b(tr(user, "btn_support"), "m:help")]
    app = miniapp_url()
    if app:
        last.append(_b(tr(user, "btn_app"), web_app=types.WebAppInfo(url=app)))
    rows.append(last)
    return Screen(tr(user, "menu_title"), _kb(rows))


# --- store ----------------------------------------------------------------
def store(user) -> Screen:
    plans = list(active_plans())
    if not plans:
        return Screen(tr(user, "store_empty"), _kb([_nav(user)]))
    rows = []
    o = open_order(user)
    if o:
        rows.append([_b(tr(user, "btn_open_order", id=o.id), f"o:{o.id}")])
    cats = categories(user, plans)
    if product_display_mode() == "grouped" and len(cats) > 1:
        rows += [[_b(f"{lbl} ({len(ps)})", f"c:{i}")] for i, (lbl, ps) in enumerate(cats)]
        return Screen(tr(user, "store_title"), _kb(rows + [_nav(user)]))
    rows += [[_b(plan_button_label(user, p), f"p:{p.id}")] for p in plans]
    return Screen(tr(user, "store_plans", cat=tr(user, "btn_buy")[2:]), _kb(rows + [_nav(user)]))


def category(user, idx: int) -> Screen:
    cats = categories(user, list(active_plans()))
    if not 0 <= idx < len(cats):
        return store(user)
    label, plans = cats[idx]
    rows = [[_b(plan_button_label(user, p), f"p:{p.id}")] for p in plans]
    return Screen(tr(user, "store_plans", cat=html.escape(label)), _kb(rows + [_nav(user, "m:buy")]))


def plan_detail(user, plan) -> Screen:
    desc = pick(user, plan.desc_fa, plan.desc_en)
    lines = [f"🛒 <b>{html.escape(plan_name(user, plan))}</b>"]
    if desc:
        lines.append(html.escape(desc.strip())[:600])
    lines.append("")
    if plan.type == PlanType.CUSTOM_VOLUME:
        lines.append(tr(user, "plan_vol", v=tr(user, "selectable", lo=plan.min_gb or 1, hi=plan.max_gb or "∞")))
        lines.append(tr(user, "plan_price_gb", p=money(user, plan.price_per_gb or 0)))
    else:
        lines.append(tr(user, "plan_vol", v=tr(user, "unlimited") if not plan.data_limit else tr(user, "gb", n=plan.data_limit // GB)))
    lines.append(tr(user, "plan_days", d=tr(user, "no_expiry") if not plan.duration_days else tr(user, "days", n=plan.duration_days)))
    if plan.device_limit:
        lines.append(tr(user, "plan_devices", n=plan.device_limit))
    if plan.discount_percent and plan.type != PlanType.CUSTOM_VOLUME:
        lines.append(tr(user, "plan_discount", d=int(plan.discount_percent)))
    if plan.type != PlanType.CUSTOM_VOLUME:
        lines.append(tr(user, "plan_price", p=money(user, plan.final_price)))
    return Screen("\n".join(lines), _kb([[_b(tr(user, "btn_buy_plan"), f"pb:{plan.id}")], _nav(user, "m:buy")]))


def terms(user) -> Screen:
    return Screen(tr(user, "terms"), _kb([[_b(tr(user, "btn_accept"), "t:ok")],
                                          [_b(tr(user, "btn_read_rules"), "m:rules")], _nav(user, "m:buy")]))


def invoice(user, order, *, reused: bool = False) -> Screen:
    lines = [tr(user, "invoice", id=order.id, plan=html.escape(plan_name(user, order.plan)),
                amount=money(user, order.amount_unique))]
    if order.discount_amount:
        lines.append(tr(user, "inv_discount", orig=money(user, order.original_amount), off=money(user, order.discount_amount),
                        code=html.escape(order.discount_code_text or "")))
    if reused:
        lines += ["", tr(user, "invoice_reused")]
    cards = list(BankCard.objects.filter(is_active=True).order_by("sort_order", "id"))
    lines.append("")
    if cards:
        lines.append(tr(user, "cards"))
        lines += [f"<code>{c.card_number}</code> — {html.escape(c.holder_name)}" for c in cards]
    else:
        lines.append(tr(user, "no_cards"))
    if order.unique_expire_at:
        left = max(int((order.unique_expire_at - timezone.now()).total_seconds() // 60), 0)
        lines += ["", tr(user, "deadline", t=to_jalali_str(order.unique_expire_at, "%H:%M"), m=left)]
    lines += ["", tr(user, "send_receipt")]
    return Screen(_clip("\n".join(lines)), _kb([[_b(tr(user, "btn_check"), f"o:{order.id}:st")], _nav(user, "m:buy")]))


def discount_ask(user) -> Screen:
    return Screen(tr(user, "dc_ask"), _kb([[_b(tr(user, "btn_dc_enter"), "dc:enter")],
                                           [_b(tr(user, "btn_dc_skip"), "dc:skip")]]))


def discount_ok(user, q) -> Screen:
    return Screen(tr(user, "dc_ok", code=html.escape(q["code"]), orig=money(user, q["original"]),
                     off=money(user, q["discount"]), final=money(user, q["final"])),
                  _kb([[_b(tr(user, "btn_dc_go"), "dc:go")], [_b(tr(user, "btn_dc_other"), "dc:enter"),
                                                              _b(tr(user, "btn_dc_skip"), "dc:skip")]]))


def discount_bad(user, err: str) -> Screen:
    return Screen(tr(user, "dc_bad", err=html.escape(err)), _kb([[_b(tr(user, "btn_dc_skip"), "dc:skip")]]))


def order_status(user, order) -> Screen:
    icon, fa, en = ORDER_STATUS.get(order.status, ("•", order.status, order.status))
    lines = [tr(user, "order_status", id=order.id, st=f"{icon} {pick(user, fa, en)}")]
    pay = getattr(order, "payment", None)
    if pay is not None:
        lines.append(tr(user, "tx_line", tx=pay.tx_number))
    if order.status == OrderStatus.PENDING_PAYMENT and pay and pay.status == PaymentStatus.PENDING:
        lines.append(tr(user, "receipt_pending"))
    elif order.status == OrderStatus.PENDING_PAYMENT:
        lines.append(tr(user, "send_receipt"))
    elif order.status == OrderStatus.REJECTED:
        lines.append(tr(user, "rejected_reason", r=html.escape((pay.reject_reason if pay else "") or "—")))
    rows = []
    if order.status == OrderStatus.PENDING_PAYMENT:
        rows.append([_b(tr(user, "btn_check"), f"o:{order.id}:st")])
    if order.status == OrderStatus.COMPLETED and order.service_id:
        lines.append(tr(user, "ready"))
        rows.append([_b(tr(user, "btn_svcs"), f"s:{order.service_id}")])
    rows.append(_nav(user, "m:history"))
    return Screen("\n".join(lines), _kb(rows))


# --- services ---------------------------------------------------------------
def _pager(user, prefix: str, page: int, pages: int):
    if pages <= 1:
        return None
    row = []
    if page > 0:
        row.append(_b(tr(user, "btn_prev"), f"{prefix}:{page - 1}"))
    row.append(_b(tr(user, "page", p=page + 1, n=pages), "noop"))
    if page < pages - 1:
        row.append(_b(tr(user, "btn_next"), f"{prefix}:{page + 1}"))
    return row


def services(user, page: int = 0) -> Screen:
    from ..shop import user_services

    svcs = list(user_services(user))
    if not svcs:
        return Screen(tr(user, "svcs_empty"), _kb([[_b(tr(user, "btn_buy"), "m:buy")], _nav(user)]))
    pages = (len(svcs) + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, pages - 1))
    rows, blocks = [], []
    for s in svcs[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]:
        icon, fa, en = SERVICE_STATUS.get(s.status, ("•", s.status, s.status))
        rows.append([_b(f"{icon} {s.panel_username} · {pick(user, fa, en)}", f"s:{s.id}")])
        blocks.append(service_line(user, s, icon, pick(user, fa, en)))
    rows.append(_pager(user, "m:svcs", page, pages))
    rows.append(_nav(user))
    text = tr(user, "svcs_title", n=len(svcs)) + "\n\n" + "\n\n".join(blocks)
    return Screen(_clip(text), _kb(rows))


def service_line(user, s, icon: str, status: str) -> str:
    """Stored numbers only (no panel call per row): name + status, usage, expiry."""
    used = round(s.data_used / GB, 1)
    total = "∞" if not s.data_limit else round(s.data_limit / GB, 1)
    lines = [f"{icon} <b>{html.escape(s.panel_username)}</b> · {status}", "📊 " + tr(user, "svc_usage", u=used, t=total)]
    if s.expire_at:
        lines.append("🗓 " + tr(user, "svc_expiry", d=to_jalali_str(s.expire_at, "%Y/%m/%d"),
                                n=max((s.expire_at - timezone.now()).days, 0)))
    return "\n".join(lines)


def service_text(user, svc) -> str:
    from apps.panel.services import refresh_watchable_services

    if refresh_watchable_services([svc]):
        svc.refresh_from_db()
    icon, fa, en = SERVICE_STATUS.get(svc.status, ("•", svc.status, svc.status))
    used = round(svc.data_used / GB, 1)
    total = "∞" if not svc.data_limit else round(svc.data_limit / GB, 1)
    lines = [f"📦 <b>{html.escape(svc.panel_username)}</b>", tr(user, "svc_status", s=f"{icon} {pick(user, fa, en)}"),
             tr(user, "svc_usage", u=used, t=total)]
    if svc.status == "on_hold" and not svc.expire_at:
        days = round((svc.on_hold_duration or 0) / 86400)
        lines.append(tr(user, "svc_onhold", d=tr(user, "svc_onhold_days", n=days) if days else ""))
    elif svc.expire_at:
        left = max((svc.expire_at - timezone.now()).days, 0)
        lines.append(tr(user, "svc_expiry", d=to_jalali_str(svc.expire_at, "%Y/%m/%d"), n=left))
    else:
        lines.append(tr(user, "svc_timeless"))
    return "\n".join(lines)


def service_detail(user, svc) -> Screen:
    rows = []
    if svc.subscription_url:
        rows.append([_b(tr(user, "btn_link"), f"s:{svc.id}:link"), _b(tr(user, "btn_qr"), f"s:{svc.id}:qr")])
        rows.append([_b(tr(user, "btn_revoke"), f"s:{svc.id}:revoke"), _b(tr(user, "btn_renew"), f"s:{svc.id}:rn")])
    else:
        rows.append([_b(tr(user, "btn_renew"), f"s:{svc.id}:rn")])
    rows.append(_nav(user, "m:svcs"))
    return Screen(service_text(user, svc), _kb(rows))


def service_link(user, svc) -> Screen:
    text = tr(user, "link_text", u=html.escape(svc.subscription_url)) if svc.subscription_url else tr(user, "no_link")
    return Screen(f"📦 <b>{html.escape(svc.panel_username)}</b>\n\n{text}",
                  _kb([[_b(tr(user, "btn_qr"), f"s:{svc.id}:qr")], _nav(user, f"s:{svc.id}")]))


def service_qr(user, svc, *, title: str = "") -> Screen:
    caption = "\n\n".join(p for p in (f"<b>{html.escape(title)}</b>" if title else "", service_text(user, svc),
                                      tr(user, "link_text", u=html.escape(svc.subscription_url))) if p)[:1024]
    return Screen(caption, _kb([_nav(user, f"s:{svc.id}")]), photo=qr_png(svc.subscription_url))


def revoke_confirm(user, svc) -> Screen:
    return Screen(tr(user, "revoke_confirm"), _kb([
        [_b(tr(user, "btn_revoke_yes"), f"s:{svc.id}:revoke:yes")], [_b(tr(user, "btn_cancel"), f"s:{svc.id}")]]))


def renew_plans(user, svc) -> Screen:
    plans = [p for p in active_plans() if p.panel_id in (None, svc.panel_id) and p.type != PlanType.CUSTOM_VOLUME]
    rows = [[_b(plan_button_label(user, p), f"rn:{svc.id}:{p.id}")] for p in plans]
    return Screen(tr(user, "renew_title", name=html.escape(svc.panel_username)), _kb(rows + [_nav(user, f"s:{svc.id}")]))


# --- history ------------------------------------------------------------------
MANUAL_TYPES = ("manual", "imported")


def history_item(user, o) -> str:
    """One order as a small block: status + number, plan, account, the amount
    really paid (unique amount) or "manual service", Jalali date, reject reason."""
    icon, fa, en = HIST_STATUS.get(o.status, ("•", o.status, o.status))
    typ = pick(user, *ORDER_TYPE.get(o.type, (o.type, o.type)))
    lines = [f"{icon} <b>{tr(user, 'hist_order', id=o.id)}</b> · {pick(user, fa, en)}",
             f"📦 {html.escape(plan_name(user, o.plan)) if o.plan_id else ''}{' · ' if o.plan_id else ''}{typ}"]
    account = o.requested_account_name or (o.service.panel_username if o.service_id and o.service else "")
    if account:
        lines.append(tr(user, "hist_account", a=html.escape(account)))
    manual = o.type in MANUAL_TYPES or not o.amount_unique
    lines.append(tr(user, "hist_manual") if manual else tr(user, "hist_paid", m=money(user, o.amount_unique)))
    lines.append(tr(user, "hist_date", d=to_jalali_str(o.created_at, "%Y/%m/%d %H:%M")))
    pay = getattr(o, "payment", None)
    if pay is not None:
        lines.append(tr(user, "tx_line", tx=pay.tx_number))
    if o.status == OrderStatus.REJECTED and pay and pay.reject_reason:
        lines.append(tr(user, "hist_reason", r=html.escape(pay.reject_reason)[:120]))
    return "\n".join(lines)


def history(user, page: int = 0) -> Screen:
    qs = Order.objects.filter(user=user).select_related("plan", "payment", "service").order_by("-created_at")
    total = qs.count()
    if not total:
        return Screen(tr(user, "hist_empty"), _kb([[_b(tr(user, "btn_buy"), "m:buy")], _nav(user)]))
    pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, pages - 1))
    blocks, rows = [], []
    for o in qs[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]:
        blocks.append(history_item(user, o))
        if o.status == OrderStatus.PENDING_PAYMENT:
            rows.append([_b(f"⏳ #{o.id} — {tr(user, 'btn_check')[2:]}", f"o:{o.id}")])
    rows.append(_pager(user, "m:history", page, pages))
    rows.append(_nav(user))
    return Screen(_clip(tr(user, "hist_title", n=total) + "\n\n" + "\n\n".join(blocks)), _kb(rows))


# --- account --------------------------------------------------------------------
def invite_links(user) -> list[str]:
    links = []
    if BOT_USERNAME["value"]:
        links.append(f"https://t.me/{BOT_USERNAME['value']}?start=ref_{user.referral_code}")
    links.append(f"{site_url()}/register?ref={user.referral_code}")
    return links


def account(user) -> Screen:
    links = invite_links(user)
    text = tr(user, "acc", u=html.escape(user.username), phone=user.phone or tr(user, "not_set"),
              code=user.referral_code, n=user.referral_count,
              links="\n".join(f"<code>{html.escape(u)}</code>" for u in links))
    share = f"https://t.me/share/url?url={quote(links[0])}&text={quote(tr(user, 'share_text', site=SiteConfig.load().site_name_fa))}"
    return Screen(text, _kb([[_b(tr(user, "btn_share"), url=share)],
                             [_b(tr(user, "btn_pwd"), "m:pwd"), _b(tr(user, "btn_lang"), "m:lang")], _nav(user)]))


# --- rules / guide / support ------------------------------------------------------
_TAG = re.compile(r"<[^>]+>")


def _page_text(user, slug: str) -> str | None:
    page = Page.objects.filter(slug=slug, is_active=True).first()
    if not page:
        return None
    body = pick(user, page.body_fa, page.body_en) or ""
    body = html.escape(_TAG.sub("", body).replace("&nbsp;", " ")).strip()
    if len(body) > 3300:
        body = body[:3300].rsplit("\n", 1)[0] + tr(user, "page_more")
    return body


def rules(user) -> Screen:
    body = _page_text(user, "rules") or tr(user, "page_missing")
    rows = [[_b(tr(user, "btn_site"), url=f"{site_url()}/terms")]] if site_url().startswith("https://") else []
    return Screen(_clip(f"{tr(user, 'rules_title')}\n\n{body}"), _kb(rows + [_nav(user)]))


def guide(user) -> Screen:
    body = _page_text(user, "tutorial")
    text = tr(user, "guide_title") + (f"\n\n{body}" if body else "")
    rows, row = [], []
    for key, fa, en, *_ in OS_APPS:
        row.append(_b(pick(user, fa, en), f"ga:{key}"))
        if len(row) == 2:
            rows.append(row); row = []
    rows += [row] if row else []
    return Screen(_clip(text), _kb(rows + [_nav(user)]))


def guide_os(user, os_key: str) -> Screen:
    item = next((x for x in OS_APPS if x[0] == os_key), OS_APPS[0])
    _, fa, en, apps_fa, apps_en = item
    return Screen(tr(user, "guide_os", os=pick(user, fa, en), apps=pick(user, apps_fa, apps_en)),
                  _kb([[_b(tr(user, "btn_svcs"), "m:svcs")], _nav(user, "m:guide")]))


SUPPORT_SPLIT = re.compile(r"[\s,،]+")


def support_contacts(cfg) -> list[tuple[str, str]]:
    """[(shown, url)] from the bot's own support ids, else the site one."""
    raw = (cfg.bot_support_telegram or "").strip() or (cfg.support_telegram or "").strip()
    out = []
    for item in SUPPORT_SPLIT.split(raw):
        item = item.strip()
        if not item:
            continue
        if item.startswith("http"):
            out.append((item, item))
        else:
            h = item.lstrip("@")
            if h:
                out.append((f"@{h}", f"https://t.me/{h}"))
    return out[:4]


def support(user) -> Screen:
    cfg = SiteConfig.load()
    contacts = support_contacts(cfg)
    custom = (pick(user, cfg.bot_support_text_fa, cfg.bot_support_text_en) or cfg.bot_support_text_fa or "").strip()
    if not contacts and not custom:
        return Screen(tr(user, "support_soon"), _kb([_nav(user)]))
    shown = " · ".join(html.escape(h) for h, _ in contacts)
    if custom:
        text = tr(user, "support_title") + "\n\n" + html.escape(custom)[:3000]
        if shown:
            text += "\n\n" + tr(user, "support_ids", h=shown)
    else:
        text = tr(user, "support", h=shown)
    if len(contacts) == 1:
        rows = [[_b(tr(user, "btn_support_chat"), url=contacts[0][1])]]
    else:
        rows = [[_b(tr(user, "btn_support_chat_n", h=h), url=u)] for h, u in contacts]
    return Screen(_clip(text), _kb(rows + [_nav(user)]))


def join_channels(user, channels) -> Screen:
    rows = []
    for ch in channels:
        ident = str(ch.channel_id)
        url = ch.invite_link or (f"https://t.me/{ident.lstrip('@')}" if ident.startswith("@") else None)
        if url:
            rows.append([_b(tr(user, "btn_join", c=ch.title or ident), url=url)])
    rows.append([_b(tr(user, "btn_joined"), "g:re")])
    return Screen(tr(user, "join_channels"), _kb(rows))


def is_en_user(user) -> bool:   # re-export for the router
    return is_en(user)
