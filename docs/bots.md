# Telegram bots

Two bots, configured in the admin panel → **Telegram bots** (tokens are stored
encrypted in the DB; `BOT_*_TOKEN` in `.env` only seeds an empty install).

| Bot | Container | Job |
|-----|-----------|-----|
| sales bot | `bot_sales` | customers: buy / renew, services, history, account, rules, guide, support, Mini App |
| backup bot | `bot_backup` | sends each DB backup to `backup_chat_id` |

Code: `backend/apps/telegram/` — `bot/screens.py` (every screen as a pure
function, tested with the DB only), `bot/texts.py` (fa/en, Latin digits),
`bot/sales_bot.py` (routing; each screen **edits the current message in place**),
`shop.py` (buy / renew / receipt helpers over `apps.orders`).

## Gates
Forced channels (the bot must be an admin of each) and a shared phone number are
checked on every update. With the phone gate on, `/start` only greets and asks for the
phone — no account exists until the user shares their **own** contact. The shared
phone (normalized) then decides: an existing site account → Telegram is linked to it and
it keeps its username + password («حساب سایت شما به تلگرام متصل شد؛ با همان نام کاربری و
رمز قبلی وارد شوید»); an account already linked to another Telegram id → refused + staff
alerted; nothing → a new account with a random username + password.

## Main menu
🛒 Buy · 📦 My services · 🧾 Purchase history · 👤 My account · 📜 Rules ·
📚 Connection guide · 💬 Support · 🌐 Mini App (when `MINIAPP_URL` / the public URL
is https). An open, unpaid order adds "🧾 Continue open order #N" on top.

callback_data stays ≤ 64 bytes and old buttons still in users' chats keep working
(see the docstring of `bot/screens.py` for the full list).

## 💬 Support
Admin panel → **Branding → Telegram bot support**:

- **Bot support IDs** — one or more `@id` or `https://t.me/...` links, separated by
  commas or spaces (max 4 buttons). Empty → the site's *Support Telegram* field.
- **Support message (fa / en)** — free text, e.g. working hours and response time.
  English falls back to the Persian text when empty.

The screen shows the message, the IDs, and one "💬 Message support" button per ID.
With neither IDs nor a message it says the contact will be announced soon.

## 🧾 Purchase history
Six orders per page, one block per order separated by a blank line:

```
✅ سفارش #42 · تکمیل‌شده
📦 استاندارد 60 · خرید جدید
👤 اکانت: pouya_main
💳 مبلغ: 250,430 تومان
🗓 1405/07/18 18:05
```

- the amount is the **unique amount actually paid** (`amount_unique`), not the plan price;
- status: ⏳ در انتظار · 🔄 در حال ساخت · ✅ تکمیل‌شده · ❌ رد شده (+ `↳ دلیل: …`) · ⚠️ ناموفق · ⌛ منقضی;
- orders an admin created (`manual`, `imported`, or amount 0) show **🛠 سرویس دستی (ادمین)**
  instead of "0 تومان";
- dates are Jalali with Latin digits. Pending orders get a "check payment" button.

*My services* lists the same way (status, usage, expiry from the stored numbers —
opening one service refreshes it from the panel). Broadcast notifications arrive as
`🔔 <b>title</b>` + body (HTML-escaped).

## QR photos
Every subscription QR the customer gets — bot photo after purchase/renewal, the
*QR* button, the site's QR modal and its download — is
`apps/common/qrcard.py::qr_card_png`: the **untouched** code (black on white,
4-module quiet zone, integer pixel modules, no logo/text) on a white rounded card
centred on a 1080×1080 background.

Admin panel → **Branding → Subscription QR background** picks one background for
everything: *Plain* (bare code), six built-in brand designs (`caspian-light`,
`caspian-dark`, `ocean-waves`, `geometric-green`, `network`, `aurora` — JPEGs in
`backend/apps/common/qr_backgrounds/`, re-created by its `generate.py`), or a
custom upload (JPEG/PNG/WebP, ≤ 5 MB, 512–8000 px per side; cover-cropped to a
square). Each picker tile is a server-rendered preview with a sample QR.
Tests decode the composed image on every background (`zxing-cpp`).

## Running / restarting
`docker compose restart bot_sales` (code changes need `./update.sh` first — the
code is baked into the image). Logs: `docker compose logs -f bot_sales`.
