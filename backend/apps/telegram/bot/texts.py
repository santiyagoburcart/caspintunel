"""Bilingual (fa / en) texts for the sales bot — same wording as the user site.
Digits are always Latin (0-9). Pick with `tr(user, key, **fmt)`."""
from __future__ import annotations

T: dict[str, tuple[str, str]] = {
    # --- main menu ---
    "menu_title": ("🏠 <b>منوی اصلی</b>\nیک گزینه را انتخاب کنید:", "🏠 <b>Main menu</b>\nChoose an option:"),
    "btn_buy": ("🛒 خرید سرویس", "🛒 Buy a service"),
    "btn_svcs": ("📦 سرویس‌های من", "📦 My services"),
    "btn_history": ("🧾 سوابق خرید", "🧾 Purchase history"),
    "btn_acc": ("👤 حساب من", "👤 My account"),
    "btn_rules": ("📜 قوانین", "📜 Rules"),
    "btn_guide": ("📚 راهنمای اتصال", "📚 Connection guide"),
    "btn_support": ("💬 پشتیبانی", "💬 Support"),
    "btn_tickets": ("🎫 پشتیبانی / تیکت‌ها", "🎫 Support / tickets"),
    "btn_staff_tickets": ("📥 تیکت‌ها (پرسنل)", "📥 Tickets (staff)"),
    "btn_app": ("🌐 ورود به مینی‌اپ", "🌐 Open the mini app"),
    "btn_site": ("🌐 ورود به سایت", "🌐 Open the website"),
    "btn_open_order": ("🧾 ادامهٔ سفارش باز #{id}", "🧾 Continue open order #{id}"),
    "btn_back": ("⬅️ بازگشت", "⬅️ Back"),
    "btn_home": ("🏠 منوی اصلی", "🏠 Main menu"),
    "btn_prev": ("« قبلی", "« Prev"),
    "btn_next": ("بعدی »", "Next »"),
    "page": ("صفحهٔ {p} از {n}", "Page {p} of {n}"),
    "error": ("⚠️ مشکلی پیش آمد. لطفاً دوباره تلاش کنید.", "⚠️ Something went wrong. Please try again."),
    "welcome": ("👋 به ربات <b>{site}</b> خوش آمدید.", "👋 Welcome to <b>{site}</b>."),
    "welcome_new": ("\n\nیک حساب سایت برای شما ساخته شد:\nنام کاربری: <code>{u}</code>\nرمز عبور: <code>{p}</code>\n"
                    "با همین مشخصات می‌توانید وارد سایت شوید.",
                    "\n\nA website account was created for you:\nUsername: <code>{u}</code>\nPassword: <code>{p}</code>\n"
                    "You can sign in on the website with these."),
    # --- store ---
    "store_title": ("🛒 <b>خرید سرویس</b>\nیک دسته را انتخاب کنید:", "🛒 <b>Buy a service</b>\nPick a category:"),
    "store_plans": ("🛒 <b>{cat}</b>\nیک پلن را انتخاب کنید:", "🛒 <b>{cat}</b>\nPick a plan:"),
    "store_empty": ("فعلاً پلنی برای فروش فعال نیست.", "No plans are on sale right now."),
    "other": ("سایر", "Other"),
    "plan_vol": ("📦 حجم: {v}", "📦 Volume: {v}"),
    "plan_days": ("⏳ مدت: {d}", "⏳ Duration: {d}"),
    "plan_devices": ("📱 تعداد دستگاه: {n}", "📱 Devices: {n}"),
    "plan_price": ("💳 قیمت: <b>{p}</b>", "💳 Price: <b>{p}</b>"),
    "plan_price_gb": ("💳 قیمت هر گیگ: <b>{p}</b>", "💳 Price per GB: <b>{p}</b>"),
    "plan_discount": ("🏷 تخفیف: {d}%", "🏷 Discount: {d}%"),
    "unlimited": ("نامحدود", "Unlimited"),
    "no_expiry": ("بدون انقضا", "No expiry"),
    "days": ("{n} روز", "{n} days"),
    "gb": ("{n} گیگ", "{n} GB"),
    "selectable": ("دلخواه ({lo} تا {hi} گیگ)", "Your choice ({lo}–{hi} GB)"),
    "btn_buy_plan": ("✅ خرید این پلن", "✅ Buy this plan"),
    "ask_gb": ("📦 چند گیگابایت می‌خواهید؟ یک عدد بین {lo} و {hi} بفرستید.", "📦 How many GB? Send a number between {lo} and {hi}."),
    "bad_gb": ("⚠️ حجم باید عددی بین {lo} و {hi} باشد. دوباره بفرستید:", "⚠️ The volume must be a number between {lo} and {hi}. Send it again:"),
    "ask_name": ("✏️ یک نام دلخواه برای اکانت بفرستید (حروف و اعداد انگلیسی، مثل <code>ali2</code>):",
                 "✏️ Send a name for the account (English letters and digits, e.g. <code>ali2</code>):"),
    "bad_name": ("⚠️ {err}\nیک نام دیگر بفرستید:", "⚠️ {err}\nSend another name:"),
    "terms": ("📜 <b>پذیرش قوانین</b>\nپیش از خرید، قوانین سرویس را بخوانید و بپذیرید.",
              "📜 <b>Accept the rules</b>\nRead and accept the service rules before buying."),
    "btn_accept": ("✅ قوانین را می‌پذیرم", "✅ I accept the rules"),
    "btn_read_rules": ("📜 خواندن قوانین", "📜 Read the rules"),
    "cancelled": ("لغو شد.", "Cancelled."),
    # --- invoice / order ---
    "invoice": ("🧾 <b>فاکتور سفارش #{id}</b>\n{plan}\n\nمبلغ دقیق قابل پرداخت:\n<b>{amount}</b>\n"
                "⚠️ دقیقاً همین مبلغ را واریز کنید تا پرداخت خودکار تأیید شود.",
                "🧾 <b>Invoice — order #{id}</b>\n{plan}\n\nExact amount to pay:\n<b>{amount}</b>\n"
                "⚠️ Pay exactly this amount so the payment is confirmed automatically."),
    "invoice_reused": ("ℹ️ این همان سفارش باز قبلی شماست؛ با همان مبلغ پرداخت کنید.",
                       "ℹ️ This is your earlier open order; pay the same amount."),
    "cards": ("💳 شمارهٔ کارت (برای کپی بزنید):", "💳 Card number (tap to copy):"),
    "no_cards": ("⚠️ کارتی برای واریز ثبت نشده — با پشتیبانی تماس بگیرید.", "⚠️ No card is set up — please contact support."),
    "deadline": ("⏰ مهلت پرداخت: تا {t} ({m} دقیقه)", "⏰ Pay by {t} ({m} min left)"),
    "send_receipt": ("📸 پس از واریز، <b>عکس رسید</b> را همین‌جا بفرستید.", "📸 After paying, send the <b>receipt photo</b> here."),
    "btn_check": ("🔄 بررسی وضعیت پرداخت", "🔄 Check payment status"),
    "order_status": ("🧾 <b>سفارش #{id}</b>\nوضعیت: {st}", "🧾 <b>Order #{id}</b>\nStatus: {st}"),
    "receipt_pending": ("📸 رسید شما ثبت شده و در انتظار تأیید ادمین است.", "📸 Your receipt is waiting for admin approval."),
    "receipt_ok": ("✅ رسید شما دریافت شد و در انتظار تأیید ادمین است. پس از تأیید، سرویس آماده می‌شود.",
                   "✅ Receipt received — waiting for admin approval. Your service is prepared once it is approved."),
    "receipt_fail": ("⚠️ ثبت رسید ناموفق بود: {err}\nلطفاً دوباره تلاش کنید.", "⚠️ The receipt could not be saved: {err}\nPlease try again."),
    "receipt_not_image": ("لطفاً عکس رسید را بفرستید (تصویر).", "Please send the receipt as an image."),
    "no_open_order": ("سفارش بازی برای پرداخت ندارید. برای خرید «🛒 خرید سرویس» را بزنید.",
                      "You have no open order to pay. Tap “🛒 Buy a service”."),
    "rejected_reason": ("❌ دلیل رد: {r}\nبرای خرید دوباره، یک سفارش جدید ثبت کنید.", "❌ Reason: {r}\nPlace a new order to buy again."),
    "ready": ("🎉 سرویس شما آماده است.", "🎉 Your service is ready."),
    # --- services ---
    "svcs_title": ("📦 <b>سرویس‌های من</b> ({n})", "📦 <b>My services</b> ({n})"),
    "svcs_empty": ("هنوز سرویسی ندارید.", "You have no services yet."),
    "svc_status": ("وضعیت: {s}", "Status: {s}"),
    "svc_usage": ("مصرف: {u} از {t} گیگ", "Usage: {u} of {t} GB"),
    "svc_expiry": ("انقضا: {d} ({n} روز مانده)", "Expires: {d} ({n} days left)"),
    "svc_onhold": ("⏳ با اولین اتصال فعال می‌شود{d}", "⏳ Starts on the first connection{d}"),
    "svc_onhold_days": (" (اعتبار {n} روز)", " ({n} days)"),
    "svc_timeless": ("بدون محدودیت زمان", "No time limit"),
    "btn_link": ("🔗 لینک اشتراک", "🔗 Subscription link"),
    "btn_qr": ("📷 QR", "📷 QR"),
    "btn_revoke": ("♻️ تغییر لینک ساب", "♻️ Change sub link"),
    "btn_renew": ("🔄 تمدید", "🔄 Renew"),
    "link_text": ("🔗 لینک اشتراک (برای کپی بزنید):\n<code>{u}</code>", "🔗 Subscription link (tap to copy):\n<code>{u}</code>"),
    "no_link": ("این سرویس هنوز لینک اشتراک ندارد.", "This service has no subscription link yet."),
    "revoke_confirm": ("⚠️ با تغییر لینک ساب، همهٔ دستگاه‌های متصل با لینک فعلی قطع می‌شوند و باید با لینک جدید دوباره وصل شوند. ادامه می‌دهید؟",
                       "⚠️ Changing the subscription link disconnects every device using the current link; they must reconnect with the new one. Continue?"),
    "btn_revoke_yes": ("✅ بله، لینک تغییر کند", "✅ Yes, change the link"),
    "btn_cancel": ("✖️ انصراف", "✖️ Cancel"),
    "revoked": ("✅ لینک ساب تغییر کرد.", "✅ The subscription link was changed."),
    "revoke_fail": ("⚠️ تغییر لینک ناموفق بود: {err}", "⚠️ Could not change the link: {err}"),
    "renew_title": ("🔄 <b>تمدید {name}</b>\nپلن تمدید را انتخاب کنید:", "🔄 <b>Renew {name}</b>\nPick a renewal plan:"),
    # --- history ---
    "hist_title": ("🧾 <b>سوابق خرید</b> ({n})", "🧾 <b>Purchase history</b> ({n})"),
    "hist_empty": ("هنوز خریدی ثبت نشده است.", "No purchases yet."),
    "hist_order": ("سفارش #{id}", "Order #{id}"),
    "hist_account": ("👤 اکانت: <code>{a}</code>", "👤 Account: <code>{a}</code>"),
    "hist_paid": ("💳 مبلغ: <b>{m}</b>", "💳 Amount: <b>{m}</b>"),
    "hist_manual": ("🛠 سرویس دستی (ادمین)", "🛠 Manual service (admin)"),
    "hist_date": ("🗓 {d}", "🗓 {d}"),
    "hist_reason": ("↳ دلیل: {r}", "↳ Reason: {r}"),
    # --- account ---
    "acc": ("👤 <b>حساب من</b>\n\nنام کاربری: <code>{u}</code>\nموبایل: {phone}\nزبان: فارسی\n\n"
            "🎁 کد معرف شما: <code>{code}</code>\nتعداد دعوت‌شده‌ها: {n}\n\nلینک دعوت (برای کپی بزنید):\n{links}",
            "👤 <b>My account</b>\n\nUsername: <code>{u}</code>\nPhone: {phone}\nLanguage: English\n\n"
            "🎁 Your referral code: <code>{code}</code>\nPeople invited: {n}\n\nInvite link (tap to copy):\n{links}"),
    "btn_pwd": ("🔑 تغییر رمز عبور", "🔑 Change password"),
    "btn_lang": ("🌐 English", "🌐 فارسی"),
    "btn_share": ("📤 اشتراک‌گذاری لینک دعوت", "📤 Share invite link"),
    "share_text": ("با این لینک در {site} ثبت‌نام کن:", "Join {site} with this link:"),
    "ask_pwd": ("🔑 رمز عبور جدید را بفرستید (حداقل 8 کاراکتر). پیام شما بلافاصله پاک می‌شود.",
                "🔑 Send the new password (at least 8 characters). Your message is deleted right away."),
    "pwd_bad": ("⚠️ رمز عبور نامعتبر: {err}\nدوباره بفرستید:", "⚠️ Invalid password: {err}\nSend it again:"),
    "pwd_ok": ("✅ رمز عبور تغییر کرد.", "✅ Password changed."),
    "not_set": ("ثبت نشده", "not set"),
    # --- pages / help / support ---
    "rules_title": ("📜 <b>قوانین</b>", "📜 <b>Rules</b>"),
    "guide_title": ("📚 <b>راهنمای اتصال</b>\nسیستم‌عامل دستگاه خود را انتخاب کنید:", "📚 <b>Connection guide</b>\nPick your device's system:"),
    "guide_os": ("📚 <b>راهنمای اتصال — {os}</b>\n\nنرم‌افزارهای پیشنهادی: {apps}\n\n"
                 "1️⃣ لینک اشتراک سرویس را از «📦 سرویس‌های من» کپی کنید.\n"
                 "2️⃣ در برنامه، افزودن از کلیپ‌بورد (Import) یا اسکن QR را بزنید.\n"
                 "3️⃣ سرورها را به‌روزرسانی و سپس دکمهٔ اتصال را لمس کنید.",
                 "📚 <b>Connection guide — {os}</b>\n\nRecommended apps: {apps}\n\n"
                 "1️⃣ Copy your subscription link from “📦 My services”.\n"
                 "2️⃣ In the app, import from clipboard or scan the QR code.\n"
                 "3️⃣ Update the server list, then tap connect."),
    "page_more": ("\n\n… متن کامل در سایت.", "\n\n… full text on the website."),
    "page_missing": ("این صفحه هنوز تنظیم نشده است.", "This page is not set up yet."),
    "support": ("💬 <b>پشتیبانی</b>\n\nبرای هر سؤال یا مشکل به پشتیبانی پیام دهید: {h}", "💬 <b>Support</b>\n\nMessage support for any question or problem: {h}"),
    "support_title": ("💬 <b>پشتیبانی</b>", "💬 <b>Support</b>"),
    "support_ids": ("📨 {h}", "📨 {h}"),
    "support_soon": ("💬 <b>پشتیبانی</b>\n\nراه ارتباطی پشتیبانی به‌زودی اعلام می‌شود.", "💬 <b>Support</b>\n\nThe support contact will be announced soon."),
    "btn_support_chat": ("💬 پیام به پشتیبانی", "💬 Message support"),
    "btn_support_chat_n": ("💬 پیام به {h}", "💬 Message {h}"),
    # --- gates ---
    "join_channels": ("📢 برای استفاده از ربات ابتدا در کانال‌های زیر عضو شوید:", "📢 Join these channels first to use the bot:"),
    "btn_join": ("عضویت در {c}", "Join {c}"),
    "btn_joined": ("✅ عضو شدم، بررسی کن", "✅ I joined, check again"),
}

ORDER_STATUS = {
    "pending_payment": ("⏳", "در انتظار پرداخت", "Awaiting payment"),
    "paid": ("✅", "تأیید شد، در حال ساخت سرویس", "Approved, preparing your service"),
    "completed": ("✅", "تکمیل شد", "Completed"),
    "rejected": ("❌", "رد شد", "Rejected"),
    "failed": ("⚠️", "ناموفق", "Failed"),
    "expired": ("⌛", "منقضی (مهلت پرداخت تمام شد)", "Expired (payment window passed)"),
}
SERVICE_STATUS = {
    "active": ("🟢", "فعال", "Active"), "on_hold": ("⏳", "در انتظار اولین اتصال", "Waiting for first connection"),
    "expired": ("🔴", "منقضی", "Expired"), "limited": ("🟠", "اتمام حجم", "Out of data"),
    "disabled": ("⚫️", "غیرفعال", "Disabled"), "pending": ("🔵", "در حال ساخت", "Being prepared"),
}
# short labels for list messages (history)
HIST_STATUS = {
    "pending_payment": ("⏳", "در انتظار", "Pending"),
    "paid": ("🔄", "در حال ساخت", "Preparing"),
    "completed": ("✅", "تکمیل‌شده", "Completed"),
    "rejected": ("❌", "رد شده", "Rejected"),
    "failed": ("⚠️", "ناموفق", "Failed"),
    "expired": ("⌛", "منقضی", "Expired"),
}
ORDER_TYPE = {"new": ("خرید جدید", "New"), "renew": ("تمدید", "Renewal"), "addon_volume": ("حجم اضافه", "Add-on"),
              "manual": ("دستی", "Manual"), "imported": ("انتقالی", "Imported")}
OS_APPS = [  # same lists as the site's Help page
    ("android", "اندروید", "Android", "v2rayNG، NekoBox", "v2rayNG, NekoBox"),
    ("ios", "آیفون (iOS)", "iPhone (iOS)", "Streisand، Shadowrocket", "Streisand, Shadowrocket"),
    ("windows", "ویندوز", "Windows", "v2rayN، NekoRay", "v2rayN, NekoRay"),
    ("mac", "مک‌اواس", "macOS", "V2Box، Streisand", "V2Box, Streisand"),
]


def is_en(user) -> bool:
    return getattr(user, "language", "fa") == "en"


def tr(user, key: str, **fmt) -> str:
    fa, en = T[key]
    text = en if is_en(user) else fa
    return text.format(**fmt) if fmt else text


def pick(user, fa: str, en: str) -> str:
    return en if is_en(user) else (fa or en)


def money(user, amount) -> str:
    n = f"{int(amount or 0):,}"
    return f"{n} T" if is_en(user) else f"{n} تومان"
