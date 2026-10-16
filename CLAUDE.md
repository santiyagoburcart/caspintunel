# CLAUDE.md — working notes for caspintunel

Read `PROGRESS.md` first (build state, phase log, open items). This file holds
the **durable rules and gotchas**. Keep both short; don't duplicate them.

## Stack & layout
- Django 5.2 + DRF + Celery + Channels (Redis) + **MySQL 8 in prod** · React 18 + Vite + Tailwind SPAs:
  `frontend/user` at `/`, `frontend/admin` at `/panel/` (Vite `base:/panel/`).
- Panel = **PasarGuard v5.3.0 over HTTP only** (`apps/panel/client.py`), never vendored.
  Verified live: `GET /api/users?search=&limit=` → `{"users":[…],"total":n}`; user objects carry
  `hwid_limit` (null = unlimited), `group_ids`, `note`, `on_hold_expire_duration`, `admin`.
- **This server runs PROD** (`docker-compose.yml` + `docker-compose.prod.yml`; `.env` sets `COMPOSE_FILE`
  so plain `docker compose …` means prod): nginx → built SPAs, gunicorn (`web`), daphne (`/ws/`), celery
  worker/beat, both bots. Code is **baked into images** — a backend/frontend change is live only after
  `./update.sh` (backup → pull → build → one-off migrate/seed/collectstatic → **rolling** swap of web,
  daphne, both SPAs behind healthchecks → plain up for the rest). Migrations run while the previous release
  still serves: keep them backward compatible (add now, drop next release). Prod uses `volumes: !override` / `!reset` so none of the dev
  bind mounts leak in. The dev compose alone (`docker compose -f docker-compose.yml`, `./update.sh --dev`)
  is for development machines only (runserver + Vite, `./backend` bind-mounted).
- `./update.sh` first dumps the DB to `backups/pre-update-<ver>-<ts>.sql.gz` and tags the running app images
  `:rollback`, then pulls/builds/ups. **Rollback: `./update.sh --rollback`** (images only; restore the dump
  if a migration must be undone). Build images only through `update.sh`: with the containerd image store a
  manual `docker compose build` drops the previous image, so there is nothing left to tag.
- Prod `web` does NOT migrate/collectstatic on boot (`RUN_MIGRATIONS=0`, dev still does); `update.sh` and
  `install.sh` run them. `seed` must stay idempotent and must never overwrite admin-panel values.
- Tests: **only** `./scripts/test.sh [pytest args]` — isolated stack (`docker-compose.test.yml`, project
  `caspintunel-test`, own network, throw-away MySQL + Redis on tmpfs, per-run keys, nothing from `.env`).
  Browser checks: Playwright image `mcr.microsoft.com/playwright:v1.49.1-noble` against the live site with
  writes blocked in-browser (never create fake data in the prod DB).

## Safety (hard rules — live site with real users)
- **Never run tests, scripts or verification commands against the live database or live Redis.** All tests
  use the isolated test stack above. `config/settings/test.py` refuses to start unless the DB host is
  `test-db` and Redis hosts are `test-redis`; production names/addresses are refused even if allow-listed.
  Never bypass or weaken that guard.
- **Ask first, in chat, and wait for an explicit "yes"** before any command that could flush, delete,
  truncate or overwrite live data: Redis `FLUSHDB`/`FLUSHALL`/`DEL` on live keys, SQL `DROP`/`TRUNCATE`/
  `DELETE` or `UPDATE` without a `WHERE`, `docker volume rm` / `docker compose down -v`, `rm -rf` on data
  dirs (`backups/`, `mail/`, `nginx/letsencrypt/`, `/data/`), restoring a DB dump, `git clean` in the repo.
  Don't put such a command in a script "for later" or behind an echo — if unsure, don't run it.
- Read-only inspection of live state (SELECTs, `redis-cli --scan`, logs, `docker inspect`) is fine. Live
  verification may only issue read requests or writes that are blocked in-browser.
- Before running a one-off container on the live network (`caspintunel_default`), remember the image
  entrypoint migrates the DB unless `RUN_MIGRATIONS=0` / `--entrypoint` is set.

## Conventions
- API-first under `/api/v1/`; admin API `/api/v1/admin/…` uses the **separate `Staff` model** + staff JWT +
  `StaffPermission`: `perms_map` per method, `action_perms` per viewset action (wins over `perms_map`).
- Every admin write that matters → `write_audit(action=…, staff=request.user, target=…)`.
- Payments move to `approved` ONLY via `payments_sms.services.approve_payment` (it fulfils, notifies, records the
  confirmer; idempotent) and to `rejected` only via `reject_payment` (closes the order). Never set `payment.status`
  to approved/rejected directly. Rejected / expired / completed orders are never reused by `create_order`.
- **SMS amounts: one explicit unit, exact match only** (`payments_sms/parsing.py::deposit_amount`): unit from the
  SMS (ریال/تومان/Rial/IRR/Toman), else `SmsSource.amount_unit` (default Rial); converted to tomans ONCE. An order
  auto-confirms only when that equals `amount_unique` exactly. Never add tolerance or ×10/÷10 retries — unit
  look-alikes are logged as "amount mismatch" (SMS log filter) and never approved. (Incident 2026-10-15, order #46.)
- Panel operations: **panel first, then read the account back and mirror it** (`apply_user_to_service`);
  only send changed fields (`update_service`). Never delete a panel account when "disable" is meant.
- Users are **soft-deleted** only (`apps/accounts/deletion.py`); hard `DELETE /admin/users/<id>/` is 405
  (it would cascade orders/payments and change revenue). Deleted users are excluded from lists, stats,
  pickers, referral codes, scheduled renewals.
- Phones: always through `apps/accounts/phone.py` (`normalize_ir_phone` → `09xxxxxxxxx`); uniqueness is
  app-level. A Telegram contact that matches a site account merges the bot account into it
  (`telegram/accounts.py::link_telegram_phone`) and invalidates the unverified site password.
- Staff JWTs carry `tv` = `Staff.token_version`; always resolve the staff with
  `adminpanel.tokens.staff_for_payload()` (never a bare `Staff.objects.get(pk=payload[...])`). Password change or
  `manage.py revoke_staff_sessions [--username X]` ends staff sessions (customers untouched). Spent refresh
  jtis live in the DB (`StaffRevokedToken`), never only in Redis.
- JWT: `CHECK_REVOKE_TOKEN` + tolerant `apps.accounts.authentication.JWTAuthentication` (claim-less old
  tokens still accepted; unusable-password accounts rejected). Password change returns a fresh pair.
- Live updates: WebSocket `/ws/notifications/` (customer JWT) and `/ws/admin/payments/` (staff JWT +
  `payment.view`) via `apps/notifications/live.py::push_payments_event` (sent on commit).
- Frontend: fa/en for every string (per-page `T = {fa, en}` or `lib/i18n.jsx`), Jalali via `lib/format.js`.
  **Digits are always Latin 0-9** in both languages (amounts, dates `1405/07/03`, badges, %, bot text);
  every `fa` Intl formatter needs `-u-nu-latn`. Persian/Arabic digits are only normalized on INPUT
  (`user/src/lib/phone.js`, `accounts/phone.py`, `payments_sms/parsing.py`). Themes: Caspian (light/dark), Midnight Aurora, Royal Frost. Colours come from
  `var(--c-*)` except these **fixed** tokens: toggles `--toggle-on #11AB53` / `--toggle-off` dark gray;
  ConfirmDialog tone colours (danger red, success #11AB53, primary #1464BA, warning amber).
- **One popup for everything**: `components/ConfirmDialog.jsx` (identical in both SPAs) + `useConfirm()`.
  Never use `window.confirm/alert/prompt`. **One copy helper**: `lib/clipboard.js::copyToClipboard`.
- Fonts are bundled (`@fontsource`, no CDN): fa = Vazirmatn, en = Inter, `<code>` = JetBrains Mono.
- Mobile (≤767px, Caspian admin): bottom nav + Settings page = index of every page not in the bottom nav.
  A new admin page must be reachable from the sidebar **and** that index (+ `MOBILE_TITLES`).
  Phone density: record-grid cards (not stacked tables), KPI tiles 2 per row, subtitles hidden, inputs 16px,
  targets ≥44px. Badge/pill **text** uses `--c-*-fg` (contrast-safe); "expired" is always `muted` gray.
- Subscription QR = `apps/common/qrcard.py::qr_card_png` everywhere (bot, site modal, downloads): never
  restyle the code itself (black on white, 4-module quiet zone, integer modules); backgrounds are bundled
  JPEGs (`qr_backgrounds/generate.py`) or the Branding upload. Bot support IDs/text live in `SiteConfig`.
- Admin "Documentation" serves only `docs/*.md` (secret-looking `NAME=value` lines masked). Keep docs free
  of real values; new docs show up automatically.
- The rejected Liquid Glass refresh is archived at tag `archive/ui-refresh-liquid-glass` — don't copy from it.

## Gotchas (learned the hard way)
- `useEffect(load, [])` where `load` returns a Promise breaks under StrictMode (dev server). Always
  `useEffect(() => { load() }, [])`.
- **Two migrations with the same name** from different sessions: Django trusts the name, not the schema.
  After merging someone else's migrations, compare real columns with the models (`accounts.0008` exists
  because an unmerged `0006` draft had been applied to this DB).
- MySQL DDL cannot run inside a transaction: data/schema-repair migrations using raw DDL need `atomic = False`.
- A `position: fixed` child of a `backdrop-filter` element is positioned relative to that element — render
  overlays/sheets through a portal to `<body>`.
- `--c-surface` is translucent in dark themes; solid panels need `var(--c-bg)` underneath.
- CSS grids: an implicit/`1fr` column grows to its longest item (e.g. a subscription URL) and overflows
  phones. Use `grid-cols-1` / `minmax(0,1fr)` / `repeat(auto-fit, minmax(min(100%,Npx),1fr))` + `min-w-0`.
- Media: nginx serves `/media/` from the volume except `/media/receipts/` + `/media/apps/` (404); receipts go
  through the auth-checked API → `X-Accel-Redirect` to internal `/_protected_media/` (private, no-store).
- Client IP: nginx gives Django exactly one trusted address (`$client_ip` map; XFF overwritten) and DRF
  has `NUM_PROXIES = 1`. Don't switch back to `$proxy_add_x_forwarded_for` — a spoofed header would pick
  its own throttle bucket. Same rule for `X-Forwarded-Proto` (`$fwd_proto`, trusted only from 127.0.0.1).
- Throttles: anon 180/min, user 600/min, `public_read` 600/min (`/config/ /theme/ /pages/ /plans/`, also
  cached 60s in Redis via `apps/common/public_cache.py`, bumped by save/delete signals), strict `auth`
  10/min and `receipt` 20/hour. A new model feeding a public endpoint must be added to the signal list.
- UI audits against the live server: keep concurrency low; never switch the live active theme
  (intercept `/api/v1/theme/` instead).
- Tests that call `transaction.on_commit` work need `@pytest.mark.django_db(transaction=True)` and a stubbed
  `fulfill_order.delay` (no panel in tests). Bot handler tests must stub `close_old_connections`.

## Agency panel (apps/agency, docs/agency.md)
- 1:1 port of PAMP v1.5.3 (reseller admins). Formulas, sync order and enforcement are VERBATIM (PORTING.md);
  `tests/test_golden.py` compares them with the ORIGINAL PAMP code — never "improve" them here.
- `agency_sync_enabled` / `agency_enforcement_enabled` stay OFF until the owner approves the cut-over from the
  Finland PAMP (never two syncs on one panel). Resellers are NOT `accounts.User` rows.
- Real PAMP data (dumps, recorded panel responses) lives only in `backups/pamp/` and `backend/.golden_local/`.

## Server migration (docs/migration.md)
- `scripts/migrate-export.sh [--final|--resume]` (old server) → encrypted archive + manifest;
  `scripts/migrate-import.sh ARCHIVE | --start-workers | --status` (new server); `scripts/migrate-check.sh IP`
  (pre-DNS test, read-only). Test the toolkit only with `scripts/test-migration.sh` (throw-away `migtest-*` stacks).
- Maintenance mode = file `nginx/flags/maintenance` (503 for everything except ACME). Worker hold =
  `MIGRATION_HOLD=1` in `.env`: `entrypoint.sh` keeps bots + celery idle (survives restarts and `update.sh`).
  Never run `--final`, `--resume` or an import on the live server without being asked: they stop/replace live state.
- The import keeps the target's own `DB_*`, `COMPOSE_FILE`, `SERVER_IP`; everything else (incl. `SECRET_KEY`,
  `FIELD_ENCRYPTION_KEY`) comes from the source. A new server-specific `.env` key must be added to `KEEP_KEYS`.

## Operator phone tools
- Android SMS Bridge: `mobile_sms/` (Kotlin); the APK in `mobile_sms/release/` is served by the panel.
- **iPhone Shortcut: single source `mobile_shortcut/CaspinSMS.shortcut`** (XML plist, no secrets; endpoint +
  token are import questions). **Official distribution = an iCloud link** (setting `ios_shortcut_icloud_url`,
  validated `https://www.icloud.com/shortcuts/<id>`, edited on Apps & tools; button + QR). iOS 15+ refuses
  unsigned files and this Linux server can't sign, so the panel's built file is only the "Advanced: unsigned"
  download (`shortcuts sign --mode anyone` on a Mac). A token never goes into the iCloud link or a page URL.
  **Shortcut change = update the repo file + bump `mobile_shortcut/VERSION` + changelog in
  `mobile_shortcut/README.md` + re-import on an iPhone, re-share as a NEW iCloud link, update the setting.**
  Keep the two action UUIDs the backend looks for.

## Telegram
- Mini app: the WebApp SDK is BUNDLED (`@twa-dev/sdk`, never the telegram.org CDN); initData is also read from
  `#tgWebAppData`. `POST /auth/telegram/miniapp/` has `authentication_classes = []` (a stale JWT must never block it),
  validates with the DB sales-bot token, applies the phone gate. Inside Telegram the SPA never shows a login form.
- Sales bot: screens are pure functions in `apps/telegram/bot/screens.py` (texts fa/en in `bot/texts.py`); the
  router in `sales_bot.py` EDITS the current message; typed steps live in the cache (`tgbot:state:<tg_id>`).
  callback_data ≤64 bytes; keep old callback names working (users' chat history). Tests use a fake bot, never
  the live one.

## Secrets / .env
- Mail: every app email uses `EMAIL_BACKEND = apps.common.mail.DynamicEmailBackend`, which picks the server
  at send time: **admin-panel relay (`EmailSettings`, enabled) → `.env` `EMAIL_*` (external host) → local
  `mailserver`** (`SMTP_ONLY`; needs `SMTP_RELAY_*` since this server blocks outbound 25). The web app never
  touches the mailserver container. Settings are cached 30 s per process + a version key bumped on save
  (password never in Redis). Status (`last_success_at`/`last_error`) is written on every send. Always send
  through `send_mail`/`EmailMessage` (never `smtplib` directly); UI: `/panel/settings/email`,
  permission `settings.email`.
- Nothing secret in git: `.env` (gitignored, backups `.env.bak*` too), device tokens, panel/bot credentials
  live in the DB (encrypted fields where sensitive). Grep the diff for tokens before every commit.
- `.env` = infrastructure + secrets only; `.env.example` documents every variable. Panels, bot tokens, sync
  and backup intervals are **admin-panel (DB) values**; `PANEL_*` / `BOT_*_TOKEN` / `DJANGO_SUPERUSER_*`
  are seed-only (empty install) and ignored afterwards.
