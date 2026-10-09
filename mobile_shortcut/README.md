# Caspin SMS — iPhone Shortcut

**Version:** see [`VERSION`](VERSION) (currently **1.0.0**)

The iPhone equivalent of the Android SMS Bridge (`mobile_sms/`): a Shortcut that
a **Message automation** runs for every SMS from the bank, which POSTs the SMS to
the server so the matching order is auto-confirmed.

```
POST https://<your-domain>/api/v1/payments/sms/inbound/
X-Device-Token: <SMS device token>
{"text": "<message body>", "sender": "<message sender>"}
```

## Distribution — the iCloud link (official)

iOS 15+ only imports **signed** shortcuts. Opening the raw file fails with
*"Importing unsigned shortcut files is not supported"*, and signing needs macOS
or Apple's iCloud — our Linux server can't sign. So the **official
distribution is an iCloud link**, kept in the panel setting
`ios_shortcut_icloud_url` (**Apps & tools → iPhone Shortcut → Shortcut
settings**). The panel validates that it starts with
`https://www.icloud.com/shortcuts/` and has nothing after the id. The Apps page
shows **Install via iCloud** and a QR code of the link, so the iPhone can scan it
from a desktop screen.

The link never contains a token. Installing from it asks the two import
questions: the **server address** and the **device token**. The panel shows both
next to the button, with copy buttons. The token is fetched on demand and is
never placed in the link or the page URL.

### Publishing a new version (every time the shortcut changes)

1. Edit `CaspinSMS.shortcut` in this folder (see *Editing the shortcut*), bump
   [`VERSION`](VERSION) and add a changelog entry below. Commit.
2. Get the file onto a Mac, sign it
   (`shortcuts sign --mode anyone -i CaspinSMS.shortcut -o CaspinSMS-signed.shortcut`),
   and import it on an iPhone **without** filling in a real token. Or build the
   same shortcut directly on the iPhone.
3. On that iPhone: Shortcuts → long-press the shortcut → **Share → Copy iCloud
   Link**. Before sharing, check that the token field is empty and still an
   import question.
4. Panel → **Apps & tools → iPhone Shortcut → Shortcut settings**: paste the new
   link → **Save**. Old links keep working, but they install the old version.

## Single source of truth

- `CaspinSMS.shortcut` in this folder is the **only** source of the shortcut's
  logic. The panel's **advanced** download builds an **unsigned** file from it at
  request time (`backend/apps/settings_app/shortcut.py`). It fills in this
  server's endpoint and, if the operator ticks it, one SMS device's token. The
  injected values are never written back to disk. The panel cannot upload
  another iOS file.
- The committed file contains **no secrets**: the endpoint is the placeholder
  `https://YOUR-DOMAIN/...`, the token is empty, and both are **import
  questions**.
- **Any change to the shortcut = edit this file + bump `VERSION` + changelog
  entry + re-share a new iCloud link and update the panel setting.**

### Advanced: the unsigned file

Panel → **Apps & tools → iPhone Shortcut → Advanced: unsigned file**. This only
works if you sign it on a Mac with
`shortcuts sign --mode anyone -i CaspinSMS.shortcut -o CaspinSMS-signed.shortcut`.
⚠️ A signed file with a token inside lets **anyone** who has it post SMS to the
server as that device. Never share it or upload it anywhere. Share only the
iCloud link (no token).

## How it works (actions)

| # | Action | Notes |
|---|---|---|
| 0 | Text — server endpoint | UUID `6F1C4C2E-…7E01`; import question 1 |
| 1 | Text — device token | UUID `0B9A3D51-…1F02`; import question 2; empty in the repo |
| 2 | If *Shortcut Input* has any value | a manual run has no message → nothing is sent |
| 3 | Get Contents of URL — POST, JSON | `text` = Shortcut Input (the message), `sender` = Shortcut Input → **Sender**, header `X-Device-Token` = action 1 |
| 4–6 | Otherwise → alert, End If | explains that it must run from the Message automation |

When you run it by hand there is no Shortcut Input, so the earlier version sent
an empty `text`. That was expected; this version shows an alert instead. In the
automation, Shortcut Input is the received message, so `text` is its body and
`sender` its sender.

## Install — English

1. Panel → **Settings → SMS devices → Add device** for this iPhone.
2. Panel → **Apps & tools → iPhone Shortcut**: on the iPhone tap **Install via
   iCloud**, or scan the QR code with the iPhone camera → **Add Shortcut**.
3. While installing, enter the **server address** and the **device token** in the
   fields the shortcut asks for. The panel shows both on the same card: pick the
   device → **Show token** → copy.
4. Shortcuts → **Automation → + → Message**: *Sender* = the bank's number (or
   *Message contains* a bank keyword) → action **Run Shortcut → Caspin SMS** with
   **Shortcut Input** → turn **Run Immediately** on (and notifications off).
5. Panel → **Settings → Bank numbers**: add the bank's sender number. When that
   list is not empty, SMS from other senders are stored but not auto-confirmed.

## نصب — فارسی

1. پنل ← **تنظیمات ← دستگاه‌های SMS ← افزودن دستگاه** برای همین آیفون.
2. پنل ← **اپلیکیشن‌ها و ابزارها ← شورتکات آیفون**: روی آیفون **نصب از iCloud**
   را بزنید یا کد QR را با دوربین آیفون اسکن کنید ← **Add Shortcut**.
3. **هنگام نصب، توکن را در فیلد خواسته‌شده وارد کنید.** آدرس سرور و توکن
   دستگاه روی همان کارت در پنل نمایش داده می‌شوند: دستگاه را انتخاب کنید ←
   **نمایش توکن** ← کپی.
4. Shortcuts ← **Automation ← + ← Message**: فرستنده = شمارهٔ بانک (یا «پیام
   شامل» کلمهٔ کلیدی بانک) ← اکشن **Run Shortcut ← Caspin SMS** با
   **Shortcut Input** ← گزینهٔ **Run Immediately** را روشن کنید.
5. پنل ← **تنظیمات ← شماره‌های بانکی**: شمارهٔ فرستندهٔ بانک را اضافه کنید. اگر
   این فهرست خالی نباشد، پیامک فرستنده‌های دیگر ذخیره می‌شود ولی خودکار تأیید نمی‌شود.

### انتشار نسخهٔ جدید (هر بار که شورتکات تغییر کند)

1. فایل `CaspinSMS.shortcut` را ویرایش کنید، `VERSION` را بالا ببرید و تغییرات
   را در Changelog پایین بنویسید.
2. فایل را روی مک امضا کنید
   (`shortcuts sign --mode anyone -i CaspinSMS.shortcut -o CaspinSMS-signed.shortcut`)
   و **بدون توکن واقعی** روی یک آیفون وارد کنید.
3. روی همان آیفون: Shortcuts ← نگه داشتن شورتکات ← **Share ← Copy iCloud Link**.
4. پنل ← **اپلیکیشن‌ها و ابزارها ← شورتکات آیفون ← تنظیمات شورتکات**: لینک جدید
   را جای‌گذاری و **ذخیره** کنید.

⚠️ فایل امضاشده‌ای که توکن داخلش است را با هیچ‌کس به اشتراک نگذارید. برای
اشتراک‌گذاری فقط از لینک iCloud (بدون توکن) استفاده کنید.

## Editing the shortcut

The file is an XML property list, so it is readable and diffable. To change it
in the Shortcuts app instead: import it, edit it, export the unsigned file, run
`plutil -convert xml1 CaspinSMS.shortcut`, then put the endpoint and token
actions back to their placeholders:
- keep the two action UUIDs above, because the panel finds them by UUID;
- endpoint `https://YOUR-DOMAIN/api/v1/payments/sms/inbound/`, token empty;
- keep both import questions.

Then bump `VERSION` and add a changelog entry.

## Changelog

### Distribution — 2026-10-09 (shortcut unchanged, VERSION stays 1.0.0)
- iOS 15+ rejects the unsigned panel download ("Importing unsigned shortcut files
  is not supported"). The official install is now the iCloud link in the panel
  setting `ios_shortcut_icloud_url` (button + QR). Server address and token are
  shown next to it for the import questions. The unsigned file moved to an
  "Advanced" option with the signing command and a warning.

### 1.0.0 — 2026-09-25
- First version kept in the repository and served by the panel download.
- JSON body `{"text": Shortcut Input, "sender": Shortcut Input.Sender}` with
  `X-Device-Token` taken from the token action.
- Sends only when started by the Message automation (a manual run shows an alert
  instead of posting an empty `text`).
- Endpoint and token are import questions; the panel fills them in at download time.
