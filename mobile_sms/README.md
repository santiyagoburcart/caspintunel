# mobile_sms — «تأیید پیامک خودکار» (Android)

Native **Kotlin** Android app for the operator side (ours and every reseller store's — **white-label since 2.0**: the app name,
icon, package id `app.smsconfirm` and every text are neutral; nothing inside names our brand). It runs on a phone that
receives the bank's card-to-card deposit SMS and forwards each one to the store's site so payments are auto-confirmed.

**Setup (2.0):** the panel's «اپلیکیشن‌ها» page makes a **«کد راه‌اندازی»** for an SMS device — one string
`SMS1:` + base64url(JSON `{"u": "<store address>", "t": "<device token>"}`), no padding
(`backend/apps/payments_sms/device_url.py::setup_code`). In the app: Settings → paste it → «اعمال و آزمایش اتصال»
(`SettingsActivity.parseSetupCode`). Typing the address + token by hand stays as the fallback.

**APKs served by the panel:** the newest `*.apk` in [`release/`](release/) (mounted read-only into `web`, so a new file is live
without a deploy). A store gets only a white-label build — a file named `sms-confirm*.apk` — and downloads it as
`sms-confirm.apk`. Current build: **`release/sms-confirm-2.0.0.apk`** (versionCode 3, release-signed, built 2026-11-14 —
served on our panel and on every store's). The old 1.1.0 build (`com.caspintunel.smsbridge.debug`) was removed in v1.60.2.

**Building (owner rule: no GitHub Actions / CI):** built on our server with a temporary toolchain that is removed afterwards
(see «Building» below), signed with **one fixed release key** kept root-only on the server (`/root/.android-signing/`, never in
git — `.gitignore` refuses `*.jks` / `*.keystore` / `*.properties` here). Every later version MUST be signed with the same key
and get a higher `versionCode`, or phones refuse the update. 2.0 has a new package id + key, so it installs **next to** the old
app (uninstall the old one after the new one works); Play Protect may warn about an unknown developer — "Install anyway".

## What it does

1. **Settings screen** — paste the panel's «کد راه‌اندازی» (or enter the server URL and the device's API token by hand),
   save them to `SharedPreferences`, and test the connection with one tap.
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
7. **Persistent notification** — "تأیید پیامک خودکار — فعال" while the
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

1. Admin panel → **Settings → SMS devices** (mobile: Settings → SMS devices) → **Add device**.
2. Give it a name (e.g. the phone's owner or model) and save — the token is
   generated and shown once; copy it (to rotate it, delete the device and add a new one).
3. In the app's Settings screen, enter:
   - **Server URL**: the base URL of the backend, e.g. `https://panel.example.com`
     (no trailing path — the app appends `/api/v1/payments/sms/...` itself)
   - **Device token**: the token you copied
4. Tap "Save and test connection" — it should report the device name back.

To revoke a device, disable or delete it in the same list;
`SmsDeviceAuthentication` rejects inactive/unknown tokens immediately.

## Configuring allowed sender numbers

The admin panel's Settings page (`/panel/settings/sms-sources`, "شماره‌های بانکی /
Bank numbers") manages the `SmsSource` rows the app filters
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
├── release/sms-confirm-<version>.apk             # release-signed APK served by the panel
└── app/
    ├── build.gradle
    └── src/main/
        ├── AndroidManifest.xml
        ├── java/app/smsconfirm/
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

`local.properties` (holding `sdk.dir=...`) is machine-specific and is not committed.

**Release build on our server** (what v2.0.0 used — ~2 GB temporary, ~4 min; remove the toolchain afterwards):

1. JDK 17 + Android command-line tools into a scratch folder; `sdkmanager "platforms;android-34" "build-tools;34.0.0"`.
2. `export JAVA_TOOL_OPTIONS=-Djava.net.preferIPv6Addresses=true` — `dl.google.com` and Google Maven answer **404 over IPv4**
   from this server (IPv6 works); the same flag goes into `SDKMANAGER_OPTS`. Keep Gradle small (`-Xmx1200m`, 1 worker,
   Kotlin in-process) — the live site shares the memory.
3. Bump `versionCode` / `versionName` in `app/build.gradle`, then `./gradlew :app:assembleRelease` (unsigned).
4. `zipalign -p 4`, then `apksigner sign --ks /root/.android-signing/sms-confirm-release.jks --ks-key-alias smsconfirm`
   (passwords in the `.properties` file next to it), `apksigner verify --print-certs` — certificate SHA-256 starts `f924b9af`.
5. Copy to `release/sms-confirm-<versionName>.apk`, remove the old one, commit.

## Installing on the phone

```bash
adb install -r mobile_sms/release/sms-confirm-2.0.0.apk
```

or copy the APK to the phone and open it (enable "install unknown apps" for
the file manager / browser used to open it — a sideload, not a Play Store install).
