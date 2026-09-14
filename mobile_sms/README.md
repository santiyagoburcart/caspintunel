# mobile_sms — CaspinTunel SMS Bridge (Android)

Native **Kotlin** Android app for the operator side. It runs on a phone that
receives the bank's card-to-card deposit SMS notifications, and forwards each
one to the CaspinTunel backend so payments can be auto-confirmed.

A pre-built debug APK is committed at
[`release/CaspinTunelSmsBridge-debug.apk`](release/CaspinTunelSmsBridge-debug.apk)
— install it directly on the operator's phone, no build step required.

## What it does

1. **Settings screen** — enter the server URL and the device's API token, save
   them to `SharedPreferences`, and test the connection with one tap.
2. **SMS listener** — a manifest-registered `BroadcastReceiver` for
   `android.provider.Telephony.SMS_RECEIVED`, backed by a **foreground
   service** so Android doesn't kill the app, with a `BOOT_COMPLETED`
   receiver so it comes back after a reboot.
3. **Sender filtering** — the app fetches the allowed bank-sender numbers from
   `.../api/v1/payments/sms/sources/` (same device token) and caches them
   locally. An SMS is only logged/forwarded if its sender matches one of
   those numbers (matched the same way the backend itself matches senders —
   last 10 digits, either side a suffix of the other, so a short code and a
   full MSISDN for the same sender both work). If no sources are configured
   yet, everything is forwarded (matches the backend's own fail-open
   behavior for an empty allow-list) and the main screen shows a warning.
   The cache refreshes after every successful ping/reconnect, opportunistically
   when it's more than 30 minutes old and an SMS arrives, and on a 30-minute
   WorkManager periodic job while the foreground service is running.
4. **Forwarding** — every matching incoming SMS is logged locally (Room) and
   POSTed to `.../api/v1/payments/sms/inbound/` with the sender, full body,
   and an ISO 8601 timestamp.
5. **Main screen** — connection status (from the last ping), the list of
   monitored sender numbers (or a "هیچ شماره بانکی تعریف نشده" warning if
   none are configured), the last 20 forwarded messages with their send
   status, and a manual "test ping" button.
6. **Retry** — a failed send is retried by WorkManager up to 3 times with
   exponential backoff (30s, 60s, 120s…), then left marked as failed in the
   local log.
7. **Persistent notification** — "CaspinTunel SMS — فعال" while the
   foreground service is running.

## Authentication — important correction

The backend's `SmsDeviceAuthentication` (see
`backend/apps/payments_sms/authentication.py`) does **not** accept a `Bearer`
token. It reads the device token from the **`X-Device-Token`** header (or,
as a fallback, `Authorization: Device <token>`). The app uses
`X-Device-Token`, matching the server's actual contract — a plain
`Authorization: Bearer <token>` header, as one might otherwise assume, would
be rejected with 401.

## Creating a device token

There is currently no admin-panel UI for this — it's managed through Django
admin:

1. Log in to `/admin/` (Django admin, not `/panel/`) with a superuser account.
2. Go to **Payments_sms → Sms app devices → Add**.
3. Give it a `name` (e.g. the phone's owner or model) and leave `is_active`
   checked. Save — the `api_token` is generated automatically.
4. Copy the generated `api_token` value.
5. In the app's Settings screen, enter:
   - **Server URL**: the base URL of the backend, e.g. `https://panel.example.com`
     (no trailing path — the app appends `/api/v1/payments/sms/...` itself)
   - **Device token**: the `api_token` you copied
6. Tap "Save and test connection" — it should report the device name back.

To revoke a device, uncheck `is_active` (or delete the row) in Django admin;
`SmsDeviceAuthentication` rejects inactive/unknown tokens immediately.

## Configuring allowed sender numbers

The admin panel's Settings page (`/panel/settings`, "شماره‌های بانکی مجاز /
Allowed SMS Sources" section) manages the `SmsSource` rows the app filters
against — add the bank's deposit-SMS sender number there (e.g. `10008556`
for Bank Mellat) and it shows up on the phone (main screen, and via
`GET /api/v1/payments/sms/sources/`) within 30 minutes, or immediately after
the next "test ping" / reconnect.

## Permissions

Requested at runtime on first launch (`RECEIVE_SMS`, `READ_PHONE_STATE`, and
`POST_NOTIFICATIONS` on Android 13+): all three must be granted for the app
to receive SMS and show its status notification. `FOREGROUND_SERVICE`,
`FOREGROUND_SERVICE_DATA_SYNC`, and `RECEIVE_BOOT_COMPLETED` are normal
(install-time) permissions and need no prompt.

## Tech stack

Kotlin · min SDK 26 (Android 8) · target/compile SDK 34 · ViewBinding · plain
XML layouts (no Compose) · Retrofit2 + OkHttp3 · Room (local log, capped at
the last 100 entries) · WorkManager (retry with backoff) · coroutines.

## Project layout

```
mobile_sms/
├── build.gradle, settings.gradle, gradle.properties
├── gradlew, gradlew.bat, gradle/wrapper/         # Gradle 8.7 wrapper
├── release/CaspinTunelSmsBridge-debug.apk        # pre-built, installable APK
└── app/
    ├── build.gradle
    └── src/main/
        ├── AndroidManifest.xml
        ├── java/com/caspintunel/smsbridge/
        │   ├── App.kt                     # notification channel setup
        │   ├── MainActivity.kt            # status + last-20 log + test ping
        │   ├── SettingsActivity.kt        # server URL + token
        │   ├── receiver/SmsReceiver.kt    # SMS_RECEIVED -> Room + WorkManager
        │   ├── receiver/BootReceiver.kt   # restarts the service after reboot
        │   ├── service/SmsForegroundService.kt
        │   ├── net/                       # Retrofit service, models, client
        │   ├── data/                      # Prefs (SharedPreferences), Room
        │   ├── repo/SmsRepository.kt      # ping + send + retry + sources cache/matching
        │   ├── work/SmsSendWorker.kt      # WorkManager retry (max 3 attempts)
        │   ├── work/SourcesRefreshWorker.kt  # 30-min periodic allowed-sender refresh
        │   └── ui/SmsLogAdapter.kt
        └── res/                           # layouts, strings (fa), icons
```

## Building

The Gradle wrapper is committed, so a normal Android Studio "Open Project"
on `mobile_sms/` works as-is. From the command line:

```bash
cd mobile_sms
# needs a JDK 17 and the Android SDK (platform 34, build-tools 34.0.0);
# point ANDROID_HOME/local.properties at your SDK if it's not on the default path
./gradlew :app:assembleDebug
# -> app/build/outputs/apk/debug/app-debug.apk
```

`local.properties` (holding `sdk.dir=...`) is machine-specific and is not
committed — create your own pointing at your Android SDK checkout before
building. A release build additionally needs a signing config, which isn't
set up here (debug builds are unsigned-but-debug-signed by AGP and install
fine with `adb install` or by sideloading).

## Installing on the phone

```bash
adb install -r mobile_sms/release/CaspinTunelSmsBridge-debug.apk
```

or copy the APK to the phone and open it (enable "install unknown apps" for
the file manager / browser used to open it — this is a debug sideload, not a
Play Store install).
