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

## Single source of truth

- `CaspinSMS.shortcut` in this folder is the **only** source. The admin panel
  (**Apps & tools → iPhone Shortcut → Download**) builds the file from it at
  download time (`backend/apps/settings_app/shortcut.py`): it fills in this
  server's endpoint and, if an SMS device is picked, that device's token. The
  injected values are never written back to disk, and the panel cannot upload
  another iOS file.
- The committed file contains **no secrets**: the endpoint is the placeholder
  `https://YOUR-DOMAIN/...`, the token is empty, and both are **import
  questions** (asked when the shortcut is added, unless the panel filled them in).
- **Any change to the shortcut = edit this file + bump `VERSION` + add a
  changelog entry below.** The panel download picks it up automatically (it is
  mounted read-only into the `web` container at `/app/mobile_shortcut`).

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
2. Panel → **Apps & tools → iPhone Shortcut**: pick that device and tap
   **Download from server**. The server address and the token are filled into
   the file. With no device picked, the token is asked when you add the shortcut.
3. iOS only imports **signed** shortcuts. On a Mac:
   `shortcuts sign --mode anyone -i CaspinSMS.shortcut -o CaspinSMS-signed.shortcut`
   (or share it once from a Mac/iPhone as an iCloud link and put the link in the
   panel).
4. Open the signed file on the iPhone → **Add Shortcut**.
5. Shortcuts → **Automation → + → Message**: *Sender* = the bank's number (or
   *Message contains* a bank keyword) → action **Run Shortcut → Caspin SMS** with
   **Shortcut Input** → turn **Run Immediately** on (and notifications off).
6. Panel → **Settings → Bank numbers**: add the bank's sender number. When that
   list is not empty, SMS from other senders are stored but not auto-confirmed.

## نصب — فارسی

۱. پنل ← **تنظیمات ← دستگاه‌های SMS ← افزودن دستگاه** برای همین آیفون.
۲. پنل ← **اپلیکیشن‌ها و ابزارها ← شورتکات آیفون**: همان دستگاه را انتخاب و
   **دانلود از سرور** را بزنید. آدرس سرور و توکن داخل فایل قرار می‌گیرد (بدون
   انتخاب دستگاه، توکن هنگام افزودن شورتکات پرسیده می‌شود).
۳. آیفون فقط شورتکات **امضاشده** را وارد می‌کند. روی یک مک:
   `shortcuts sign --mode anyone -i CaspinSMS.shortcut -o CaspinSMS-signed.shortcut`
   (یا یک بار آن را به‌صورت لینک iCloud به اشتراک بگذارید و لینک را در پنل ثبت کنید).
۴. فایل امضاشده را روی آیفون باز کنید ← **Add Shortcut**.
۵. Shortcuts ← **Automation ← + ← Message**: فرستنده = شمارهٔ بانک (یا «پیام
   شامل» کلمهٔ کلیدی بانک) ← اکشن **Run Shortcut ← Caspin SMS** با
   **Shortcut Input** ← گزینهٔ **Run Immediately** را روشن کنید.
۶. پنل ← **تنظیمات ← شماره‌های بانکی**: شمارهٔ فرستندهٔ بانک را اضافه کنید. اگر
   این فهرست خالی نباشد، پیامک فرستنده‌های دیگر ذخیره می‌شود ولی خودکار تأیید نمی‌شود.

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

### 1.0.0 — 2026-09-25
- First version kept in the repository and served by the panel download.
- JSON body `{"text": Shortcut Input, "sender": Shortcut Input.Sender}` with
  `X-Device-Token` taken from the token action.
- Sends only when started by the Message automation (a manual run shows an alert
  instead of posting an empty `text`).
- Endpoint and token are import questions; the panel fills them in at download time.
