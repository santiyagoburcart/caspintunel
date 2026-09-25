# Code-review brief — Phases 4, 5 and 6

Purpose: hand this file to a reviewer (human or AI) together with the repository.
It lists **every change** made in phases 4–6, where it lives, the intended
behaviour, how it was verified, and the known risks / assumptions worth checking.

Repository: `santiyagoburcart/caspintunel` · branch `claude/ecstatic-fermat-3w3zf4`.

| Commit | Scope | Status |
|---|---|---|
| `8a3deb4` | Phase 4 — delete user + archive, link existing panel service, HWID limit | merged in `main` (PR #1) |
| `d5b2a96` | Payments queue: no manual refresh button | merged in `main` (PR #2) |
| `a9a5815` | Phase 5 — admin mobile parity, bot QR card, sign-up terms, light-mode contrast | merged in `main` (PR #2) |
| `c1ebe36` | Phase 6 — Apps & tools page, settings routes, per-language fonts, docs | **this PR** |

Stack reminder: Django 5.2 + DRF + Celery + Channels (MySQL in prod) · React 18 +
Vite + Tailwind SPAs (`frontend/user` at `/`, `frontend/admin` at `/panel/`) ·
PasarGuard panel consumed over HTTP only · fa/en, Jalali dates.

Verification environment used for all phases: backend test suite on **SQLite**
(no MySQL available in the sandbox) — **351 tests pass** at `c1ebe36`;
`makemigrations --check` clean; both SPAs build with `vite build`; UI verified
with Playwright + Chromium against **mocked API responses** (not a live backend
or a live PasarGuard panel).

---

## Phase 4 (`8a3deb4`)

### 4.1 Soft-delete a customer (admin "Delete user")
- **Model** `backend/apps/accounts/models.py`
  - `User`: new `deleted_at` (indexed), `deleted_by` (FK `Staff`, SET_NULL), `delete_reason`; property `is_deleted`.
  - New `DeletedUserArchive`: `user` (FK, SET_NULL), `original_username/_name/_phone/_email/_telegram_id/_telegram_username`, `deleted_at`, `deleted_by` + `deleted_by_label`, `reason`, `orders_count`, `total_paid`, `snapshot` (JSON), `restored_at`, `restored_by` + `restored_by_label`.
  - Migration `accounts/0006_user_soft_delete.py` (also seeds permission `users.delete`; `seed.py` PERMISSIONS list updated too).
- **Service layer** `backend/apps/accounts/deletion.py`
  - `delete_user(user, staff, reason)`:
    1. Reason required; already-deleted → error.
    2. **Outside the DB transaction**, for each of the user's services: `apps.panel.services.disable_service_on_panel()` → PasarGuard `PUT /api/user/{name}` `{"status":"disabled"}` then `GET` to mirror. Panel 404 = "missing" (not an error). Any other `PanelError` → collected; if any failed → `UserDeletionError(failed=[…])`, **user is not touched** (services already disabled stay disabled; retry is idempotent).
    3. In one transaction: build snapshot (`build_snapshot`) → create archive → set every Service row `status=disabled` → prefix `username`/`phone`/`email` with `deleted_<id>_` (cut to column width) → `telegram_id=None`, `is_active=False`, `deleted_*` fields, append line to `admin_note` → blacklist all refresh tokens (`OutstandingToken` → `BlacklistedToken`) → audit `user.deleted`.
  - Snapshot contents: profile (incl. referral code, referrer, referral count, source, language, bank card, admin note), all orders with plan and payment (amount, method, status, bank card number/holder/bank, gateway ref, confirmer, confirmed_at, reject reason, has_receipt), all services (panel, account, plan, status before delete, status now, panel result, data limit/used, expiry, on-hold duration, device limit, subscription URL, online_at), notification counts (targeted + deliveries), totals (orders, approved payments, total paid = sum of approved payment amounts).
  - `restore_conflicts(archive)` — original username (iexact), phone, email (iexact) held by another user.
  - `restore_user(archive, staff)` — only the **latest** archive of a still-deleted user, only once; raises `RestoreConflict` (→ HTTP 409 with fields + owners); restores username/phone/email; relinks `telegram_id` **only if still free** (else warning `telegram_id_in_use`); reactivates; services **stay disabled**; audit `user.restored`.
- **API** `backend/apps/adminpanel/views/users.py`, `urls.py`
  - `POST /api/v1/admin/users/{id}/delete/ {reason}` — perm `users.delete` via new `action_perms` support in `StaffPermission` (`backend/apps/adminpanel/permissions.py`). 502 + `failed_services` when a panel call fails.
  - Hard `DELETE /admin/users/{id}/` now returns **405** (it would cascade into orders/payments).
  - User list and `stats/` exclude deleted users; retrieve/orders still work by id; editing a deleted user → 400.
  - `GET /admin/deleted-users/?search=&from=&to=&state=` (search covers original fields, reason, deleted-by, exact Telegram id) · `GET /admin/deleted-users/{id}/` (snapshot + `restore_conflicts` + `can_restore`) · `POST /admin/deleted-users/{id}/restore/` (perm `users.delete`; view = `users.view`).
  - Serializers: `UserDeleteSerializer`, `DeletedUserArchiveListSerializer`, `DeletedUserArchiveDetailSerializer`; `AdminUserSerializer` exposes `deleted_at`, `delete_reason`; `AdminServiceSerializer` adds `user_deleted`.
- **Side effects**: `apps.panel.tasks.apply_due_scheduled_renewals` skips services of deleted users. Manual-service user picker excludes deleted users.
- **Frontend (admin)**
  - `src/lib/userActions.jsx` — `useUserActions().remove(row)` (danger ConfirmDialog, required reason textarea, localized "N services could not be disabled" error) and `.restore(archive)` (409 → localized conflict text).
  - `src/pages/Users.jsx` — header link "کاربران حذف‌شده", row button "حذف کاربر" (only with `users.delete`).
  - `src/pages/UserOrders.jsx` — delete button, "deleted" banner, type tags for `manual` / `imported`.
  - `src/pages/DeletedUsers.jsx` (new) — routes `/users/deleted` (list: search, Jalali date range, state tabs, pagination, stacked cards on mobile) and `/users/deleted/:id` (profile, deletion info, orders & payments table, services with copyable sub link, restore button disabled + reason when conflicts).
- **Tests** `backend/apps/adminpanel/tests/test_user_delete.py` (9): full flow (panel PUT disabled only, never DELETE; snapshot fields; freed identifiers; sessions revoked — refresh returns 401; accounting revenue and transaction count unchanged; archive list), re-registration with the same username/email/phone and a fresh bot user for the same Telegram id, panel failure aborts, missing-on-panel is OK, reason + permission checks, hard delete 405, restore without conflicts, restore blocked by conflicts, restore with Telegram id taken, archive search/date filter/permissions.

### 4.2 Link an EXISTING PasarGuard account to a customer
- `backend/apps/panel/client.py`: `list_users(search, limit, offset)` → `GET /api/users` (returns `(users, total)`).
- `backend/apps/panel/services.py`:
  - `search_panel_users(panel, search)` — live search, each row gets `linked` (service id, owner, owner-deleted flag) via case-insensitive match against our `Service` rows.
  - `link_existing_service(user, panel, panel_username, plan=None, staff)` — refuses if already linked (`ServiceAlreadyLinked`), plan must belong to the panel, reads the account (`GET /api/user/{name}`, 404 → not found), creates our `Service` mirrored from the panel (panel's exact username spelling, `source="import"`), creates a **completed `Order` of new type `imported`, amount 0, no payment**, audit `service.linked_existing`. **Nothing is written to the panel.**
- `backend/apps/orders/models.py`: `OrderType.IMPORTED`; `Order.plan` is now **nullable** (migration `orders/0005_imported_order_type.py`). `telegram/shop.py` order history tolerates a null plan.
- API (`views/ops.py`): `GET /admin/services/panel-users/?panel=&search=` (perm `services.manage` via `action_perms`), `POST /admin/services/link/` (201; 409 already linked with owner; 400 bad plan; 404 not on panel; 502 panel error). Serializer `AdminServiceLinkSerializer`.
- Frontend `src/pages/Services.jsx`: manual-create modal now has two tabs — "ساخت سرویس جدید" (unchanged flow; field renamed "نام کاربری سرویس در پنل") and "اتصال سرویس موجود پنل" (panel → debounced live search with status, used/limit, expiry, "already linked to X" rows disabled → user picker → optional plan → "اتصال").
- Tests `test_service_link.py` (6).

### 4.3 Editable device (HWID) limit
- `update_service(..., hwid_limit)` sends `hwid_limit` to PasarGuard; `mappers.apply_user_to_service` mirrors `hwid_limit` into `Service.device_limit` (0/null → null = unlimited).
- `AdminServiceUpdateSerializer.hwid_limit` (0–1000, nullable; null → 0). Service edit page (`ServiceEdit.jsx`) has a number input (empty/0 = unlimited).
- Test in `test_service_link.py`.

---

## Payments queue follow-up (`d5b2a96`)
- `frontend/admin/src/pages/Payments.jsx`: removed the "↻ تازه‌سازی" button. The page already refetches on WebSocket events (`/ws/admin/payments/`, `usePaymentsEvents`); while the socket is **disconnected** it now polls every 15 s automatically; the live/offline pill explains this.

---

## Phase 5 (`a9a5815`)

### 5.1 Admin panel on phones (Caspian theme, ≤767px) — `frontend/admin/src/components/Layout.jsx`
- Bottom nav (5 tabs): داشبورد · کاربران · **صف پرداخت** (raised centre button, live pending-count badge from `useLivePayments`) · سرویس‌ها · تنظیمات. Active tab is computed by prefix (`activeTab()`); any page not under the first four lights up Settings.
- Mobile top bar: dark/light toggle (hidden when the theme locks the mode) + language; inner pages show back button + page title (`MOBILE_TITLES`).
- `src/pages/Settings.jsx`: on mobile the page is the **index of every page not in the bottom nav**, grouped (finance, users & sales, system & connections, general settings) + logout. (Phase 6 turned the section entries into real routes — see 6.2.)
- Shared stacked-card table rule `.rtable` in `src/index.css`, applied to `components/DataTable.jsx` (dashboard) and the Notifications history table.
- Page modals (`usr-`, `svc-`, `cd-`, `int-`, `sdm-`, `sm-` families) become full-screen sheets on phones with sticky header/footer; fixed backdrops get `margin: 0` (a parent `space-y` margin used to shift them); inputs 16px (no iOS zoom).
- `ServiceEdit.jsx`: its own mobile back button hidden (top bar provides one).
- Verified: 22 admin routes × fa/en × light/dark × 360/390 px = 176 renders, `scrollWidth ≤ viewport`, no page errors; every desktop sidebar route reachable from the bottom nav or the Settings index; desktop screenshots unchanged.

### 5.2 Bugs fixed
- **Notifications page blank** (`src/pages/Notifications.jsx`): `useEffect(load, [])` where `load` returns a Promise — React treats the return value as the cleanup; under the **dev server's StrictMode** (the compose file runs `npm run dev`) the fake cleanup throws "destroy is not a function" and the page never renders. Fixed to `useEffect(() => { load() }, [])`. Confirmed in Phase 6 by reproducing on the Vite dev server (old code: blank + error; new code: renders). A repo-wide search found no other instance.
- Services list (`Services.jsx`): status column is now a read-only pill (status is edited on the service edit page).

### 5.3 Telegram bot — service card
- `backend/apps/telegram/shop.py`: `sub_link_block()` (link in `<code>` → tap-to-copy in Telegram, HTML-escaped), `service_caption()` (≤1024 chars), `qr_png()`.
- `backend/apps/telegram/bot/sales_bot.py`: `_send_service_card()` — service detail, "QR" button, subscription revoke and completed-order check all send **one photo: QR + caption with the tap-to-copy link** and the service keyboard.
- `backend/apps/telegram/client.py`: `send_photo(..., parse_mode=None)`.
- `backend/apps/orders/tasks.py` `_notify_delivered`: site + email notification unchanged; the bot channel gets the QR service card instead of plain text (`_send_bot_service_card`); falls back to the text message only when the service has no link yet.
- Tests `telegram/tests/test_service_card.py` (2).

### 5.4 User site — login / sign-up / terms
- `frontend/user/src/pages/Login.jsx`: "حساب کاربری جدید نیاز دارید؟" is itself the link to `/register` (previously only a separate "خرید اشتراک و فعال‌سازی" button was clickable); that button removed.
- Terms accepted **once, at sign-up**: `RegisterSerializer.terms_accepted` required → `User.terms_accepted_at` (migration `accounts/0007_user_terms_accepted_at.py`); `Register.jsx` has the required checkbox; checkout no longer shows it and `OrderCreateSerializer.terms_accepted` is optional/ignored. Tests updated (`test_auth_api`, `test_phone`, `test_throttle`, `test_flow`, `test_user_delete`).
- `/rules` needs a login, so the sign-up checkbox linked into a redirect; new **public** route `/terms` (`frontend/user/src/App.jsx`) renders the same rules page; the login footer links there too.

### 5.5 Light-mode contrast
- Automated contrast audit (both SPAs × Aurora/Caspian/Frost × desktop/mobile, text contrast < 2.2:1 flagged, gradients approximated). Only real finding: Caspian light `warning` #F59E0B ≈ 2:1 on white → data migration `settings_app/0009_caspian_light_warning_contrast.py` sets it to #B45309 (dark palette untouched). No fully white-on-white element was found with mock data.

---

## Phase 6 (`c1ebe36`, this PR)

### 6.1 Apps & tools page (operator phone tools, served from our own server)
- **Model** `backend/apps/settings_app/models.py` `AppRelease` (`platform` android|ios unique, `file` in `media/apps/`, `version`, `link`, `notes`, `updated_at`, `updated_by`); migration `settings_app/0010_app_release.py`.
- **Setting** `APP_RELEASES_DIR` (default `backend/app_releases`); compose (`docker-compose.yml`, `docker-compose.prod.yml`) mounts `./mobile_sms/release` read-only there for the `web` service; `backend/.gitignore` ignores the mount point.
- **API** `backend/apps/adminpanel/views/apps.py` (perm `settings.manage`):
  - `GET /admin/apps/` — both platforms: version, size, source (`upload` | `bundled` | null), updated.
  - `POST /admin/apps/{android|ios}/` multipart — file (`.apk` for android; `.shortcut/.plist/.zip` for ios; ≤60 MB), version, link (must be http/https), notes, `clear_file`; audit `apps.release_updated`.
  - `GET /admin/apps/{platform}/download/` — uploaded file (X-Accel-Redirect in prod, streamed in dev) or, for android, the newest bundled `*.apk`; `Content-Disposition: attachment`.
- **nginx** (`nginx/conf.d/caspintunel.conf`, `nginx/prod.conf`): `location /media/apps/ { return 404; }` — files only via the authenticated API.
- **Frontend** `frontend/admin/src/pages/Apps.jsx` (route `/apps`, desktop sidebar + mobile Settings index): per-platform card with purpose, features, numbered setup steps, version/size/source chips, "Download from server" (blob download with the staff token), link to SMS devices, collapsible upload form; bottom card with copyable SMS endpoint (`{origin}/api/v1/payments/sms/inbound/`), header `X-Device-Token`, and JSON body.
- **Tests** `backend/apps/adminpanel/tests/test_apps.py` (3).

### 6.2 Mobile settings sections as real pages
- `frontend/admin/src/App.jsx`: route `/settings/:section`. `Settings.jsx` reads the section from the URL; old `/settings#section` links redirect (`replace`). On mobile the section is shown alone (injected per-section CSS) with a sticky save/reset bar; on desktop the full form is shown and scrolled to the card. New ids `sync`, `display`. Layout top bar shows the section title (`sec_*` i18n keys). `Cards.jsx` fraud link → `/settings/unique-amount`.

### 6.3 Fonts (both SPAs)
- `src/main.jsx`: only `@fontsource/vazirmatn` (400–800), `@fontsource/inter` (400–800), `@fontsource/jetbrains-mono` (400, 600) are imported — all bundled, **no CDN** (offline / Iran-only servers).
- `src/index.css`: `html[lang="fa"] body *` → Vazirmatn; `html[lang="en"] body *` → Inter with Vazirmatn fallback; only `code, pre, kbd, samp` keep JetBrains Mono (all `!important`, overriding per-theme/per-page fonts). Verified via computed styles: fa pages use only Vazirmatn, en only Inter, `<code>` JetBrains Mono.

### 6.4 Documentation updated
`docs/api.md` (rewritten: all current endpoints incl. WebSockets, SMS device API, admin table), `docs/architecture.md` (app responsibilities, beat schedule, frontend/offline/fonts/mobile nav), `docs/operations.md` (common tasks: cards, SMS devices, apps page, forced channels, delete/restore user, link existing account), `docs/offline.md`, `docs/README.md`, `README.md`, `mobile_sms/README.md` (device token created in the panel, APK downloadable from the panel).

---

## Deploy notes
```
git pull && docker compose up -d web && docker compose restart celery_worker bot_sales frontend_admin frontend_user nginx
```
`web` runs migrations on start (`accounts 0006/0007`, `orders 0005`, `settings_app 0009/0010`). `up -d web` (not just restart) is needed for the new `mobile_sms/release` mount; nginx for the `/media/apps/` rule; `bot_sales` for the new service-card message format.

## Known risks / assumptions — please check
1. **Tests ran on SQLite only**; MySQL-specific behaviour (case-insensitive collation in `panel_username__in`, JSON field) not exercised.
2. **PasarGuard API assumptions not verified against a live panel:** `GET /api/users` query params `search`/`limit`/`offset` and response `{"users": [...], "total": n}`; field name `hwid_limit` on user modify/read (0 = unlimited).
3. **Delete user**: panel calls happen before the DB transaction — a crash between them leaves services disabled on the panel for a not-deleted user (retry is idempotent). Freed phone numbers are truncated to 20 chars (`deleted_<id>_…`); originals are in the archive. Access tokens are rejected because `is_active=False` (not blacklisted individually); after a restore, an access token issued before deletion is valid again until it expires (≤ `JWT_ACCESS_MIN`).
4. **`Order.plan` is nullable** only for `imported` orders; code that assumes `order.plan` (e.g. `orders/tasks.py` fulfilment) is only reached for paid orders, which imported orders never are. Worth a check of every `order.plan.` access.
5. **Terms**: Telegram-bot / Mini App users never pass through sign-up, so their `terms_accepted_at` stays null.
6. **Font override** uses `!important` on `body *`; any intentional monospace in Persian UI outside `<code>` now renders in Vazirmatn (by request).
7. **Apps page**: the iPhone-shortcut description assumes it forwards bank SMS to `/payments/sms/inbound/`; the bundled APK is a **debug** build; download goes through a browser blob (fine for ~7 MB).
8. Settings single-section mode injects a `<style>` built from the URL section — the value is checked against a fixed whitelist (`SOLO_SECTIONS`) before use.
9. Pre-existing lint (not introduced here): unused imports in `telegram/bot/sales_bot.py` (`Service`, `plan_label`) and `orders/serializers.py` (`PlanType`).
10. UI verification used mocked API data; real data shapes were taken from the backend where possible (`/admin/monitoring|settings|roles|…` responses captured from a local SQLite instance).
