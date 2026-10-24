"""Domain wizard errors people can act on (docs/domain.md → "Errors").

Every failure of the Domain & Cloudflare page — Cloudflare API codes, public
DNS, Let's Encrypt / certbot, nginx, the switch and mail DNS — becomes
``{"key", "en", "fa", "raw"}``: a clear sentence with the fix in both languages,
plus the raw code + message, which the page shows in a small "details" line.
"""
from __future__ import annotations

import ipaddress
import re
from collections import defaultdict

# key → (en, fa). {zone} {name} {domain} {ip} {seen} {status} {type} are filled in.
MSG = {
    # ---------------------------------------------------------------- Cloudflare
    "cf_perm": (
        "The token is not allowed to edit DNS in {zone} — in Cloudflare: My Profile → API Tokens → Edit → "
        "Permissions: Zone · DNS · Edit, and Zone Resources including {zone}.",
        "توکن اجازهٔ ویرایش DNS در دامنهٔ {zone} را ندارد — در Cloudflare: My Profile → API Tokens → Edit → "
        "Permissions: Zone · DNS · Edit و Zone Resources شامل {zone}"),
    "cf_invalid": (
        "The Cloudflare token is not valid (mistyped, deleted or rolled) — in Cloudflare: My Profile → API Tokens → "
        "Create Token → template “Edit zone DNS”, then save the new token here.",
        "توکن Cloudflare معتبر نیست (اشتباه کپی شده، حذف یا عوض شده) — در Cloudflare: My Profile → API Tokens → "
        "Create Token → قالب «Edit zone DNS» توکن جدید بسازید و اینجا ذخیره کنید."),
    "cf_inactive": (
        "The token is “{status}” in Cloudflare (disabled or expired) — in My Profile → API Tokens enable it, "
        "extend its TTL or roll a new one.",
        "وضعیت توکن در Cloudflare «{status}» است (غیرفعال یا منقضی) — در My Profile → API Tokens فعالش کنید، "
        "انقضا را تمدید کنید یا توکن جدید بسازید."),
    "cf_ip": (
        "Cloudflare refuses this token from this server's IP ({ip}) — the token has an IP filter: My Profile → "
        "API Tokens → Edit → Client IP Address Filtering → add {ip} (or remove the filter).",
        "Cloudflare این توکن را از IP این سرور ({ip}) نمی‌پذیرد — توکن محدودیت IP دارد: My Profile → API Tokens → "
        "Edit → Client IP Address Filtering → {ip} را اضافه کنید (یا محدودیت را بردارید)."),
    "cf_zone": (
        "Cloudflare has no zone {zone} for this token — add the domain to this Cloudflare account (Add a site) and "
        "include it in the token's Zone Resources, or choose manual DNS.",
        "Cloudflare دامنهٔ {zone} را برای این توکن ندارد — دامنه را به همین حساب Cloudflare اضافه کنید (Add a site) "
        "و در Zone Resources توکن بگذارید، یا DNS دستی را انتخاب کنید."),
    "cf_rate": (
        "Cloudflare's rate limit was hit (too many requests) — wait about 5 minutes and try again.",
        "به محدودیت تعداد درخواست Cloudflare رسیدیم — حدود ۵ دقیقه صبر کنید و دوباره امتحان کنید."),
    "cf_exists": (
        "A record {name} already exists in {zone} and conflicts — in Cloudflare → DNS → Records delete or fix "
        "{name}, then try again.",
        "رکورد {name} از قبل در {zone} هست و تداخل دارد — در Cloudflare → DNS → Records آن را حذف یا اصلاح کنید "
        "و دوباره امتحان کنید."),
    "cf_cname": (
        "{name} is a CNAME in Cloudflare — a name can't be a CNAME and an A record at once: delete the CNAME "
        "{name} in Cloudflare → DNS → Records, then try again.",
        "{name} در Cloudflare رکورد CNAME دارد — یک نام نمی‌تواند هم CNAME باشد هم A: CNAME مربوط به {name} را "
        "در Cloudflare → DNS → Records حذف کنید و دوباره امتحان کنید."),
    "cf_record": (
        "Cloudflare rejected the record {name} — the details below say which value it did not accept.",
        "Cloudflare رکورد {name} را نپذیرفت — جزئیات زیر می‌گوید کدام مقدار پذیرفته نشد."),
    "cf_down": (
        "The Cloudflare API can't be reached from the server right now — try again in a few minutes "
        "(status: cloudflarestatus.com).",
        "API کلادفلر الان از سرور در دسترس نیست — چند دقیقهٔ دیگر دوباره امتحان کنید (وضعیت: cloudflarestatus.com)."),
    "cf_other": (
        "Cloudflare refused the request — see the details below.",
        "Cloudflare درخواست را رد کرد — جزئیات زیر را ببینید."),
    "cf_no_token": (
        "No Cloudflare token — save one above, or choose manual DNS.",
        "توکن Cloudflare تنظیم نشده — بالای صفحه ذخیره کنید یا DNS دستی را انتخاب کنید."),
    "cf_no_zones": (
        "The token is valid but sees no zone — give it Zone · Zone · Read and Zone · DNS · Edit, with Zone "
        "Resources including your domain.",
        "توکن معتبر است ولی هیچ دامنه‌ای را نمی‌بیند — دسترسی Zone · Zone · Read و Zone · DNS · Edit بدهید و "
        "دامنه را در Zone Resources بگذارید."),
    "cf_no_edit": (
        "The token is valid but may not edit DNS in any zone — in Cloudflare: My Profile → API Tokens → Edit → "
        "Permissions: Zone · DNS · Edit, and Zone Resources including your domain.",
        "توکن معتبر است ولی در هیچ دامنه‌ای اجازهٔ ویرایش DNS ندارد — در Cloudflare: My Profile → API Tokens → "
        "Edit → Permissions: Zone · DNS · Edit و Zone Resources شامل دامنهٔ شما"),
    # ---------------------------------------------------------------- public DNS (step 2)
    "dns_none": (
        "{name} has no A record in public DNS yet — create A {name} → {ip} (DNS only). New records usually "
        "appear within a few minutes; then check again.",
        "{name} هنوز در DNS عمومی رکورد A ندارد — رکورد A برای {name} با مقدار {ip} (بدون پروکسی) بسازید. "
        "رکورد جدید معمولاً تا چند دقیقه دیده می‌شود؛ بعد دوباره بررسی کنید."),
    "dns_proxied": (
        "{name} is proxied by Cloudflare (orange cloud, {seen}) — set it to “DNS only” (grey cloud) so it points "
        "straight at {ip}; certificates and mail need the real IP.",
        "{name} پشت پروکسی Cloudflare است (ابر نارنجی، {seen}) — آن را «DNS only» (ابر خاکستری) کنید تا مستقیم به "
        "{ip} اشاره کند؛ گواهی و ایمیل به IP واقعی نیاز دارند."),
    "dns_wrong": (
        "{name} points to {seen}, not this server ({ip}) — change the A record to {ip}. If you just changed it, "
        "the old value stays cached until its TTL runs out.",
        "{name} به {seen} اشاره می‌کند، نه به این سرور ({ip}) — رکورد A را روی {ip} بگذارید. اگر تازه عوضش کرده‌اید، "
        "مقدار قبلی تا پایان TTL در کش می‌ماند."),
    "dns_partial": (
        "{name} is propagating — some public resolvers already answer {ip}, others not yet. Check again in a "
        "few minutes.",
        "{name} در حال انتشار است — بعضی از DNSهای عمومی {ip} را برمی‌گردانند و بعضی هنوز نه. چند دقیقهٔ دیگر "
        "دوباره بررسی کنید."),
    "dns_doh": (
        "The server could not ask the public DNS resolvers (Cloudflare / Google DNS-over-HTTPS) — check the "
        "server's outbound HTTPS and try again.",
        "سرور نتوانست از DNSهای عمومی (DNS-over-HTTPS کلادفلر / گوگل) بپرسد — اتصال HTTPS خروجی سرور را بررسی "
        "کنید و دوباره امتحان کنید."),
    # ---------------------------------------------------------------- mail DNS
    "mail_missing": (
        "{type} {name} is not in public DNS yet — add it with the value from the table (Cloudflare: the "
        "“Publish” button does it). New records usually appear within a few minutes.",
        "{type} {name} هنوز در DNS عمومی نیست — آن را با مقدار جدول اضافه کنید (در Cloudflare دکمهٔ «ثبت» این کار "
        "را می‌کند). رکورد جدید معمولاً تا چند دقیقه دیده می‌شود."),
    "mail_mx": (
        "The MX of {name} points to {seen}, not {want} — set MX {name} → {want} (priority 10) and remove the "
        "old MX, or mail keeps going to the old server.",
        "MX دامنهٔ {name} به {seen} اشاره می‌کند، نه {want} — MX را {want} با اولویت 10 بگذارید و MX قبلی را حذف "
        "کنید، وگرنه ایمیل‌ها به سرور قبلی می‌روند."),
    "spf_multi": (
        "{name} has more than one SPF record — two “v=spf1” records make SPF fail everywhere: keep only one "
        "(the value from the table).",
        "{name} بیش از یک رکورد SPF دارد — دو رکورد «v=spf1» باعث شکست SPF می‌شود: فقط یکی (مقدار جدول) را نگه "
        "دارید."),
    "mail_diff": (
        "{type} {name} has a different value ({seen}) — replace it with the value from the table "
        "(an old DKIM key or SPF from another provider?).",
        "{type} {name} مقدار دیگری دارد ({seen}) — آن را با مقدار جدول جایگزین کنید (شاید کلید DKIM قدیمی یا SPF "
        "سرویس دیگری است)."),
    "mail_no_dkim": (
        "The DKIM key comes with the certificate step — request the certificate first.",
        "کلید DKIM در مرحلهٔ گواهی ساخته می‌شود — اول گواهی را درخواست کنید."),
    # ---------------------------------------------------------------- Let's Encrypt / certbot (step 3)
    "le_rate": (
        "Let's Encrypt rate limit for {domain} — too many attempts or certificates. Wait (1 hour after failed "
        "validations, up to a week after 5 identical certificates) and try again.",
        "محدودیت Let's Encrypt برای {domain} — تلاش یا گواهی بیش از حد. صبر کنید (یک ساعت بعد از تلاش ناموفق، تا "
        "یک هفته بعد از ۵ گواهی یکسان) و دوباره امتحان کنید."),
    "le_dns": (
        "Let's Encrypt can't find {domain} in DNS — wait until step 2 shows every name resolving to {ip} "
        "(“Check DNS”), then request the certificate again.",
        "Let's Encrypt دامنهٔ {domain} را در DNS پیدا نمی‌کند — صبر کنید تا مرحلهٔ ۲ نشان دهد همهٔ نام‌ها به {ip} "
        "می‌رسند («بررسی DNS»)، بعد دوباره درخواست گواهی بدهید."),
    "le_caa": (
        "A CAA record of {domain} does not allow Let's Encrypt — in your DNS delete the CAA record or add "
        "CAA 0 issue \"letsencrypt.org\", then try again.",
        "رکورد CAA دامنهٔ {domain} اجازهٔ صدور به Let's Encrypt نمی‌دهد — رکورد CAA را حذف کنید یا "
        "CAA 0 issue \"letsencrypt.org\" اضافه کنید و دوباره امتحان کنید."),
    "le_port80": (
        "Let's Encrypt could not connect to this server on port 80 — the A records must point at {ip} without "
        "Cloudflare proxy, and port 80 must be open (server firewall and the Hetzner Cloud firewall).",
        "Let's Encrypt نتوانست روی پورت 80 به این سرور وصل شود — رکوردهای A باید بدون پروکسی Cloudflare به {ip} "
        "اشاره کنند و پورت 80 باز باشد (فایروال سرور و فایروال Hetzner Cloud)."),
    "le_challenge": (
        "Let's Encrypt reached a server, but not this one — a name still points elsewhere or is proxied "
        "(orange cloud). Set every name to DNS only → {ip}, check DNS, then try again.",
        "Let's Encrypt به سروری رسید ولی نه این سرور — یکی از نام‌ها هنوز به جای دیگری اشاره می‌کند یا پشت پروکسی "
        "است (ابر نارنجی). همه را DNS only → {ip} کنید، DNS را بررسی کنید و دوباره امتحان کنید."),
    "le_check": (
        "The certificate for {domain} is missing, expired or does not cover every name (www / mail) — request "
        "the certificate again (step 3).",
        "گواهی {domain} وجود ندارد، منقضی شده یا همهٔ نام‌ها (www / mail) را پوشش نمی‌دهد — دوباره درخواست گواهی "
        "بدهید (مرحلهٔ ۳)."),
    "le_other": (
        "Let's Encrypt did not issue the certificate — the reason from certbot is in the details below.",
        "Let's Encrypt گواهی را صادر نکرد — دلیل certbot در جزئیات زیر آمده است."),
    "manual_cert": (
        "A manually uploaded certificate is active (nginx/manual-certs) — remove it first; the wizard manages "
        "Let's Encrypt certificates itself.",
        "یک گواهی دستی فعال است (nginx/manual-certs) — اول آن را بردارید؛ ویزارد خودش گواهی Let's Encrypt را "
        "مدیریت می‌کند."),
    "dkim_fail": (
        "The certificate was issued, but the mail server could not create the DKIM key — make sure the "
        "mailserver container is running (docker compose ps mailserver), then request the certificate again.",
        "گواهی صادر شد ولی سرور ایمیل نتوانست کلید DKIM بسازد — مطمئن شوید کانتینر mailserver اجرا است "
        "(docker compose ps mailserver)، بعد دوباره درخواست گواهی بدهید."),
    # ---------------------------------------------------------------- the switch (apply / retire / rollback)
    "nginx_test": (
        "nginx rejected the new configuration (nginx -t), so nothing was switched and the previous "
        "configuration is back — the nginx error is in the details below.",
        "nginx پیکربندی جدید را رد کرد (nginx -t)، پس چیزی عوض نشد و پیکربندی قبلی برگشت — خطای nginx در جزئیات "
        "زیر است."),
    "apply_health": (
        "After the switch https://{domain} did not answer correctly, so everything was restored automatically "
        "— check the web container logs (docker compose logs web), then try again.",
        "بعد از انتقال، https://{domain} درست پاسخ نداد، پس همه‌چیز خودکار برگشت — لاگ کانتینر web را ببینید "
        "(docker compose logs web) و دوباره امتحان کنید."),
    "apply_redirect": (
        "The old domain did not redirect to {domain} after the switch, so everything was restored automatically "
        "— see the details below.",
        "بعد از انتقال، دامنهٔ قبلی به {domain} ریدایرکت نشد، پس همه‌چیز خودکار برگشت — جزئیات زیر را ببینید."),
    "apply_container": (
        "An app container did not come up healthy with the new settings, so everything was restored "
        "automatically — check docker compose ps / logs on the server.",
        "یکی از کانتینرهای برنامه با تنظیمات جدید سالم بالا نیامد، پس همه‌چیز خودکار برگشت — روی سرور "
        "docker compose ps و لاگ‌ها را ببینید."),
    "apply_mail": (
        "The mail server did not come up as mail.{domain}, so everything was restored automatically — check "
        "docker compose logs mailserver.",
        "سرور ایمیل با نام mail.{domain} بالا نیامد، پس همه‌چیز خودکار برگشت — docker compose logs mailserver را "
        "ببینید."),
    "apply_env": (
        "The server could not update .env (permissions or disk full?), so nothing was switched.",
        "سرور نتوانست فایل .env را به‌روز کند (دسترسی یا پر بودن دیسک؟)، پس چیزی عوض نشد."),
    "apply_moved": (
        "The site's domain changed meanwhile (e.g. with ./scripts/domain.sh) — cancel this change and start "
        "a new one.",
        "دامنهٔ سایت در این فاصله عوض شده (مثلاً با ./scripts/domain.sh) — این تغییر را لغو کنید و از نو شروع کنید."),
    "rb_none": (
        "The server has no previous domain recorded, so there is nothing to roll back to.",
        "دامنهٔ قبلی روی سرور ثبت نشده، پس چیزی برای بازگشت نیست."),
    "apply_other": (
        "The server step failed and everything was restored automatically — the reason is in the details below.",
        "مرحلهٔ سرور ناموفق بود و همه‌چیز خودکار برگشت — دلیل در جزئیات زیر است."),
    # ---------------------------------------------------------------- access mode (docs/access-mode.md)
    "ax_mode": ("Choose Direct, Cloudflare proxy or Iran tunnel.", "یکی از حالت‌های مستقیم، پروکسی Cloudflare یا تونل ایران را انتخاب کنید."),
    "ax_busy": ("A mode switch is already running — wait for it to finish.", "یک تغییر حالت در حال انجام است — تا پایانش صبر کنید."),
    "ax_wizard": ("Finish or cancel the domain change first; the access mode applies to the live domain.",
                  "اول تغییر دامنه را تمام یا لغو کنید؛ حالت دسترسی روی دامنهٔ فعلی اعمال می‌شود."),
    "ax_no_iran": ("Add the Iran server's public IP first (the A record points there in tunnel mode).",
                   "اول IP عمومی سرور ایران را وارد کنید (در حالت تونل رکورد A به آن اشاره می‌کند)."),
    "ax_no_sources": ("Add the tunnel source IP(s) first — use “Auto-detect” to capture what this server sees.",
                      "اول IP(های) مبدأ تونل را اضافه کنید — با «تشخیص خودکار» آدرسی که این سرور می‌بیند را بگیرید."),
    "ax_bad_ip": ("“{name}” is not a valid {type}.", "«{name}» یک {type} معتبر نیست."),
    "ax_no_zone": ("{zone} is not in a Cloudflare zone this token can manage — the access mode needs the Cloudflare token.",
                   "{zone} در هیچ زون Cloudflare قابل‌مدیریت با این توکن نیست — حالت دسترسی به توکن Cloudflare نیاز دارد."),
    "ax_ssl": ("Cloudflare SSL/TLS mode is “{status}”; proxy mode needs Full (strict) and the token could not change it — "
               "in Cloudflare: SSL/TLS → Overview → Full (strict), or give the token Zone · Zone Settings · Edit.",
               "حالت SSL/TLS در Cloudflare «{status}» است؛ حالت پروکسی Full (strict) لازم دارد و توکن نتوانست آن را عوض کند — "
               "در Cloudflare: SSL/TLS ← Overview ← Full (strict)، یا دسترسی Zone · Zone Settings · Edit به توکن بدهید."),
    "ax_path": ("The site did not answer correctly through {name} — {seen}. Nothing was switched (or it was switched back).",
                "سایت از مسیر {name} درست پاسخ نداد — {seen}. چیزی عوض نشد (یا به حالت قبل برگشت)."),
    "ax_reverted": ("The new path failed after the DNS change, so DNS was put back to the previous mode — {seen}.",
                    "مسیر جدید بعد از تغییر DNS کار نکرد، پس DNS به حالت قبلی برگشت — {seen}."),
    "ax_edge": ("Public DNS did not return Cloudflare's addresses in time, so the proxy path could not be checked — switched back.",
                "DNS عمومی در زمان مقرر آدرس‌های Cloudflare را برنگرداند و مسیر پروکسی بررسی نشد — به حالت قبل برگشت."),
    "ax_detect": ("No request came through {name} — check that the tunnel forwards port 443 to this server.",
                  "هیچ درخواستی از مسیر {name} نرسید — بررسی کنید تونل پورت 443 را به این سرور فوروارد می‌کند."),
    # ---------------------------------------------------------------- wizard rules
    "bad_domain": ("{domain} is not a valid domain name (example: example.com).",
                   "«{domain}» نام دامنهٔ معتبری نیست (مثال: example.com)."),
    "ip_domain": ("An IP address is not a domain — enter a name like example.com.",
                  "آدرس IP دامنه نیست — نامی مثل example.com وارد کنید."),
    "same_domain": ("{domain} is already the site's domain.", "{domain} همین الان دامنهٔ سایت است."),
    "busy_change": ("Finish or cancel the current domain change first.", "اول تغییر دامنهٔ فعلی را تمام یا لغو کنید."),
    "bad_mode": ("Choose a Cloudflare zone or manual DNS.", "یک زون Cloudflare یا DNS دستی را انتخاب کنید."),
    "no_ip": ("This server's public IP is unknown — set SERVER_IP in .env.",
              "IP عمومی این سرور مشخص نیست — SERVER_IP را در .env تنظیم کنید."),
    "queued": ("Another server step is already queued — wait for it to finish (up to a minute).",
               "یک مرحلهٔ دیگر روی سرور در صف است — تا پایانش صبر کنید (حداکثر یک دقیقه)."),
    "bad_state": ("Not possible while the change is “{status}”.", "در وضعیت «{status}» این کار ممکن نیست."),
    "need_dns": ("DNS must resolve to this server first — finish step 2 (“Check DNS”).",
                 "اول DNS باید به این سرور برسد — مرحلهٔ ۲ را کامل کنید («بررسی DNS»)."),
    "need_tls": ("The certificate must be issued first (step 3).", "اول باید گواهی صادر شود (مرحلهٔ ۳)."),
    "need_mail": ("The mail records (MX, SPF, DKIM, DMARC) must be in public DNS first (step 4).",
                  "اول رکوردهای ایمیل (MX، SPF، DKIM، DMARC) باید در DNS عمومی باشند (مرحلهٔ ۴)."),
    "nothing_rb": ("Nothing to roll back — the site is not on a domain set by this wizard.",
                   "چیزی برای بازگشت نیست — سایت روی دامنه‌ای که این ویزارد تنظیم کرده نیست."),
    "bad_checklist": ("Unknown checklist item.", "مورد ناشناخته در فهرست کارها."),
}


def explain(key: str, raw: str = "", **ctx) -> dict:
    en, fa = MSG[key]
    base = {k: ("" if v is None else str(v)) for k, v in ctx.items()}

    def fill(text, i):
        v = defaultdict(str, base)
        v["zone"] = v["zone"] or ("this zone", "این دامنه")[i]
        v["name"] = v["name"] or ("the record", "رکورد")[i]
        return text.format_map(v)

    return {"key": key, "en": fill(en, 0), "fa": fill(fa, 1), "raw": (raw or "")[:600]}


# ------------------------------------------------------------------ Cloudflare API errors
PERM = {10000, 9109, 6003, 9103, 10001}
INVALID = {1000, 6111, 9106}
ZONE = {7003, 7000, 1001, 1003, 1049, 1061}
RATE = {971, 10013, 10429}
EXISTS = {81057, 81058}
CNAME = {81053, 81054, 81055}


def cloudflare(exc, zone: str = "", name: str = "", ip: str = "") -> dict:
    """CloudflareError → friendly; `raw` keeps "code: message" as Cloudflare said it."""
    codes = set(getattr(exc, "codes", ()) or ())
    status = getattr(exc, "status", None)
    text = str(exc)
    low = text.lower()
    ctx = {"zone": zone, "name": name, "ip": ip}
    if getattr(exc, "network", False) or (status or 0) >= 500:
        key = "cf_down"
    elif status == 429 or codes & RATE or "rate limit" in low:
        key = "cf_rate"
    elif ("location" in low or "ip address" in low or "client ip" in low) and (codes & PERM or status == 403):
        key = "cf_ip"
    elif codes & INVALID or "invalid api token" in low or "invalid format for authorization" in low \
            or "invalid access token" in low:
        key = "cf_invalid"
    elif codes & CNAME or "cname" in low:
        key = "cf_cname"
    elif codes & EXISTS or "already exists" in low:
        key = "cf_exists"
    elif codes & ZONE:
        key = "cf_zone"
    elif codes & PERM or status == 403:
        key = "cf_perm"
    elif 1004 in codes or any(9000 <= c < 10000 for c in codes) or status == 400:
        key = "cf_record"
    else:
        key = "cf_other"
    return explain(key, text, **ctx)


def is_permission(info: dict) -> bool:
    return info.get("key") in ("cf_perm", "cf_ip", "cf_invalid")


# ------------------------------------------------------------------ public DNS
_CF_NETS = [ipaddress.ip_network(n) for n in (
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18", "108.162.192.0/18",
    "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
    "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22")]


def cloudflare_ip(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(a in n for n in _CF_NETS)


def dns_host(name: str, ip: str, resolvers: list[dict]) -> dict | None:
    """Why `name` does not (yet) resolve to this server, from the DoH answers."""
    answered = [r for r in resolvers if "error" not in r]
    raw = " · ".join(f"{r['resolver']}: {', '.join(r.get('ips') or []) or r.get('error') or 'no answer'}" for r in resolvers)
    if not answered:
        return explain("dns_doh", raw, name=name, ip=ip)
    if all(ip in r["ips"] for r in answered):
        return None
    seen = sorted({i for r in answered for i in r["ips"] if i != ip})
    if seen and any(cloudflare_ip(i) for i in seen):
        return explain("dns_proxied", raw, name=name, ip=ip, seen=", ".join(seen))
    if any(ip in r["ips"] for r in answered):
        return explain("dns_partial", raw, name=name, ip=ip)
    if seen:
        return explain("dns_wrong", raw, name=name, ip=ip, seen=", ".join(seen))
    return explain("dns_none", raw, name=name, ip=ip)


def mail_record(rec: dict, answered: list[list[str]], resolvers: list[dict]) -> dict | None:
    """Why a mail record (MX / SPF / DMARC / DKIM) is not right yet. `answered` = plain values per resolver."""
    raw = " · ".join(f"{r['resolver']}: {' | '.join(v[:80] for v in r.get('ips') or []) or r.get('error') or 'no answer'}" for r in resolvers)
    if not answered:
        return explain("dns_doh", raw, name=rec["name"])
    ctx = {"name": rec["name"], "type": rec["type"] if rec["type"] == "MX" else _kind(rec)}
    if rec["type"] == "MX":
        hosts = sorted({v.split()[-1].rstrip(".") for vs in answered for v in vs if v.strip()})
        if not hosts:
            return explain("mail_missing", raw, **ctx)
        return explain("mail_mx", raw, seen=", ".join(hosts), want=rec["content"], **ctx)
    if rec["match"] == "v=spf1" and any(sum(v.startswith("v=spf1") for v in vs) > 1 for vs in answered):
        return explain("spf_multi", raw, **ctx)
    seen = sorted({v[:60] + ("…" if len(v) > 60 else "") for vs in answered for v in vs if v.startswith(rec["match"])})
    if not seen:
        return explain("mail_missing", raw, **ctx)
    return explain("mail_diff", raw, seen=" | ".join(seen), **ctx)


def _kind(rec: dict) -> str:
    return {"v=spf1": "SPF", "v=DMARC1": "DMARC", "v=DKIM1": "DKIM"}.get(rec.get("match") or "", rec["type"])


# ------------------------------------------------------------------ host results (certbot, nginx, switch)
_HOST = [
    (r"manual(ly uploaded)? cert", "manual_cert"),
    (r"too many (certificates|failed auth|requests|new orders)|rateLimited|rate limit", "le_rate"),
    (r"\bCAA\b", "le_caa"),
    (r"no DKIM|DKIM record|mail server is not running|could not create a DKIM", "dkim_fail"),
    (r"nginx -t", "nginx_test"),
    (r"health/ answered", "apply_health"),
    (r"does not redirect", "apply_redirect"),
    (r"mail server (answers as|did not become healthy)", "apply_mail"),
    (r"never became healthy|did not start|no new container", "apply_container"),
    (r"\.env could not", "apply_env"),
    (r"rejected: the site is on", "apply_moved"),
    (r"no previous domain", "rb_none"),
    (r"NXDOMAIN|DNS problem|SERVFAIL|no valid A|No valid IP", "le_dns"),
    (r"Timeout|timed out|Connection refused|Connection reset|connect(ion)? to .*:80|Network unreachable", "le_port80"),
    (r"unauthorized|Invalid response|\b40[34]\b", "le_challenge"),
    (r"no certificate for|has expired|does not cover", "le_check"),
]


def host(action: str, message: str, domain: str = "", ip: str = "") -> dict:
    """The host watcher's failure message → friendly (raw = what certbot / nginx / the switch said)."""
    msg = message or ""
    for pat, key in _HOST:
        if re.search(pat, msg, re.I):
            if key.startswith("le_") and key != "le_check" and action != "cert":
                continue                    # certbot wording in a switch message means something else
            return explain(key, msg, domain=domain, ip=ip)
    return explain("le_other" if action == "cert" else "apply_other", msg, domain=domain, ip=ip)
