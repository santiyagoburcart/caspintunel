# Caspin SMS — iPhone Shortcut

**Version:** see [`VERSION`](VERSION) (currently **1.1.0**)

The iPhone equivalent of the Android SMS Bridge (`mobile_sms/`): a Shortcut that
a **Message automation** runs for every SMS from the bank. Since 1.1.0 it **saves
the SMS to a queue file on the iPhone first, then uploads the whole queue**. A
bank SMS is never lost when the upload fails with "The network connection was
lost" (iOS Shortcuts has no try/catch: a failed request just stops the shortcut).

```
POST https://caspintunel.com/api/v1/payments/sms/inbound-batch/
X-Device-Token: <SMS device token>
{"text": "<message body>", "sender": "<sender>", "received_at": "2026-10-24T18:12:03+03:30"}
{"text": "…", "sender": "…", "received_at": "…"}          ← one JSON object per SMS (NDJSON)
```

The server is idempotent: re-sending the same queue never stores, matches or approves
an SMS twice, and each SMS is matched at the time the phone **received** it. An
order that expired while the SMS waited in the queue is still matched. See
[`docs/sms-batch.md`](../docs/sms-batch.md).

## How it works (actions)

| # | Action | Notes |
|---|---|---|
| 0 | Text — server endpoint | UUID `6F1C4C2E-…7E01`; import question 1 (default `https://caspintunel.com/api/v1/payments/sms/inbound-batch/`) |
| 1 | Text — device token | UUID `0B9A3D51-…1F02`; import question 2; **empty in the repo** |
| 2 | Text — bank sender (optional) | import question 3; empty = the SMS's own Sender |
| 3–15 | **If Shortcut Input has any value** (started by the Message automation) | Current Date → Format Date (ISO 8601 with time) → `Sender` variable → Dictionary `{text, sender, received_at}` → Text (JSON) → **Append to Text File `CaspinSMS-queue.txt`**, all before any network call. Otherwise (manual run / home-screen button): nothing here, so it's flush-only with no alert |
| 16–17 | Get File `CaspinSMS-queue.txt` (no error if missing) → its text | |
| 18–31 | If the queue has any value → **Get Contents of URL** (POST, body = the queue file, header `X-Device-Token`) → Get Dictionary Value `result` → **if `stored`**: read the file again, remove exactly the text that was sent (Replace Text) → save the rest (Overwrite) or delete the file if nothing is left | Anything else (network error, HTTP error, wrong token) keeps the queue for the next run |

Removing exactly the sent text (instead of deleting the file) keeps an SMS that the
automation appended while the upload was running.

## Distribution: the iCloud link (official)

iOS 15+ only imports **signed** shortcuts. Opening the raw file fails with
*"Importing unsigned shortcut files is not supported"*, and signing needs macOS
or Apple's iCloud, which our Linux server doesn't have. So the **official
distribution is an iCloud link** kept in the panel setting `ios_shortcut_icloud_url`
(**Apps & tools → iPhone Shortcut → Shortcut settings**). The Apps page shows
**Install via iCloud** and a QR code of the link. The link never contains a token:
installing from it asks the import questions (server address, device token,
optional bank sender). The panel shows the server address and the token, each with
a copy button.

### Publishing a new version (every time the shortcut changes)

1. Edit `CaspinSMS.shortcut` in this folder, bump [`VERSION`](VERSION) and add a
   changelog entry below. Commit.
2. Get the file onto a Mac and sign it
   (`shortcuts sign --mode anyone -i CaspinSMS.shortcut -o CaspinSMS-signed.shortcut`),
   then import it on an iPhone **without** filling in a real token.
3. On that iPhone: Shortcuts → long-press the shortcut → **Share → Copy iCloud Link**.
4. Panel → **Apps & tools → iPhone Shortcut → Shortcut settings**: paste the link →
   **Save**. Old links keep working, but they install the old version.

## Single source of truth

- `CaspinSMS.shortcut` in this folder is the **only** source of the shortcut's logic.
  The panel's advanced download builds an **unsigned** file from it at request time
  (`backend/apps/settings_app/shortcut.py`). It fills in this server's endpoint and,
  if the operator ticks it, one SMS device's token. Nothing injected is ever written
  back to disk.
- The committed file contains **no secrets**: the token is empty and an import
  question. The endpoint holds only the public server address.
- **Any change = edit this file + bump `VERSION` + changelog + re-share a new iCloud
  link and update the panel setting.**

⚠️ A signed file with a token inside lets **anyone** who has it post SMS to the
server as that device. Never share it or upload it anywhere. Share only the
iCloud link (no token).

## Install (English)

1. Panel → **Settings → SMS devices → Add device** for this iPhone; copy its token.
2. Install: **Install via iCloud** on the Apps page (or scan its QR code), or sign the
   file on a Mac and AirDrop it (steps in the Persian section, step 2).
3. Answer the import questions: server address (`https://caspintunel.com/api/v1/payments/sms/inbound-batch/`),
   the device token, and optionally the bank sender (e.g. `Resalat`).
4. Shortcuts → **Automation → + → Message**: *Sender* = the bank (or *Message contains*
   a bank keyword) → **Run Immediately** → action **Run Shortcut → Caspin SMS**, input
   **Shortcut Input**.
5. Optional home-screen button: long-press the shortcut → **Details → Add to Home
   Screen**, name it **ارسال صف پیامک**. Tapping it uploads the queue (no alert).
6. Test: turn on Airplane Mode, have a test SMS arrive (the automation fails at the
   upload but the SMS is already in `Files → iCloud Drive → Shortcuts → CaspinSMS-queue.txt`),
   turn Airplane Mode off, tap the home-screen button → the SMS log in the panel shows it
   with **delivered late** and the file is gone.

## نصب (فارسی)

۱. **ساخت دستگاه در پنل:** پنل ← تنظیمات ← دستگاه‌های SMS ← «افزودن دستگاه» برای همین
آیفون. توکن را کپی کنید.

۲. **امضا روی مک و انتقال با AirDrop** (اگر از لینک iCloud پنل نصب می‌کنید، به مرحلهٔ ۳ بروید):
   - فایل `CaspinSMS.shortcut` را روی مک بگیرید: از پنل ← اپلیکیشن‌ها و ابزارها ← شورتکات
     آیفون ← «پیشرفته: فایل امضانشده» ← دانلود. **تیک «توکن داخل فایل» را نزنید.**
   - Terminal را روی مک باز کنید و در پوشهٔ دانلود بزنید:
     `shortcuts sign --mode anyone -i CaspinSMS.shortcut -o CaspinSMS-signed.shortcut`
   - در Finder روی `CaspinSMS-signed.shortcut` راست‌کلیک ← Share ← **AirDrop** ← آیفون خودتان.
   - روی آیفون فایل باز می‌شود ← **Add Shortcut**.

۳. **پاسخ به سؤال‌های نصب:**
   - آدرس سرور: `https://caspintunel.com/api/v1/payments/sms/inbound-batch/`
   - توکن دستگاه: همان توکن مرحلهٔ ۱
   - فرستندهٔ بانک (اختیاری): مثلاً `Resalat`. اگر خالی بماند، فرستندهٔ خود پیامک استفاده می‌شود.

۴. **اتوماسیون:** Shortcuts ← Automation ← **+** ← **Message**:
   - Sender = شمارهٔ یا نام بانک (یا Message Contains یک کلمهٔ ثابت پیامک بانک، مثلاً «واریز»)
   - **Run Immediately** را انتخاب کنید (و «Notify When Run» را خاموش کنید)
   - اکشن: **Run Shortcut ← Caspin SMS**، ورودی را **Shortcut Input** بگذارید.

۵. **دکمهٔ «ارسال صف پیامک» روی صفحهٔ اصلی:** در Shortcuts روی Caspin SMS نگه دارید ←
**Details** (یا Share) ← **Add to Home Screen** ← نام را «ارسال صف پیامک» بگذارید ← Add.
با زدن این دکمه فقط صف ارسال می‌شود، بدون پیام خطا. اگر صف خالی باشد، کاری انجام نمی‌شود.

۶. **پنل ← تنظیمات ← شماره‌های بانکی:** شمارهٔ یا نام فرستندهٔ بانک را اضافه کنید.

۷. **آزمایش:**
   - حالت هواپیما را روشن کنید و یک پیامک آزمایشی بگیرید. ارسال خطا می‌دهد، ولی پیامک در
     `Files ← iCloud Drive ← Shortcuts ← CaspinSMS-queue.txt` ذخیره شده است.
   - حالت هواپیما را خاموش کنید و دکمهٔ «ارسال صف پیامک» را بزنید. در پنل ← لاگ پیامک‌ها، پیامک
     با برچسب «با تأخیر رسید» دیده می‌شود و فایل صف پاک شده است.

ℹ️ اگر دستگاه iCloud Drive را خاموش کرده باشد، فایل در `On My iPhone ← Shortcuts` است.

## Editing the shortcut

The file is an XML property list (readable and diffable). If you edit it in the
Shortcuts app instead: export the unsigned file, run `plutil -convert xml1`, and put
the token back to empty. Keep the two action UUIDs above (the panel finds them by
UUID) and the three import questions. Then bump `VERSION` and add a changelog entry.

## Changelog

### 1.1.0 — 2026-10-24
- **Offline queue: save first, send after.** Each SMS becomes `{text, sender, received_at}`
  (ISO 8601) JSON, appended to `CaspinSMS-queue.txt` before any network call. The whole
  queue is POSTed to `/api/v1/payments/sms/inbound-batch/` and removed only when the
  server answers `"result": "stored"`; an SMS appended during the upload is kept.
- A manual run (home-screen **ارسال صف پیامک**) only flushes the queue, with no alert
  (1.0.0 showed one).
- New optional import question: the bank sender name. Default server address
  `https://caspintunel.com/api/v1/payments/sms/inbound-batch/`.
- The server matches each SMS at the time it was received, and an order that expired
  while the SMS was queued still matches. Re-sending never processes an SMS twice.

### Distribution — 2026-10-09 (shortcut unchanged, VERSION stayed 1.0.0)
- iOS 15+ rejects the unsigned panel download, so the official install became the
  iCloud link (`ios_shortcut_icloud_url`, button + QR). The unsigned file moved to an
  "Advanced" option.

### 1.0.0 — 2026-09-25
- First version in the repository: JSON `{"text", "sender"}` POST to `/inbound/` with
  `X-Device-Token`, sent only from the Message automation (a manual run showed an alert).
