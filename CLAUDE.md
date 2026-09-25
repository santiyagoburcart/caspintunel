# CLAUDE.md — working notes for caspintunel

Read `PROGRESS.md` first (build state, phase log, open items). This file holds
the **durable rules and gotchas**. Keep both short; don't duplicate them.

## Stack & layout
- Django 5.2 + DRF + Celery + Channels (Redis) + **MySQL 8 in prod** · React 18 + Vite + Tailwind SPAs:
  `frontend/user` at `/`, `frontend/admin` at `/panel/` (Vite `base:/panel/`).
- Panel = **PasarGuard v5.3.0 over HTTP only** (`apps/panel/client.py`), never vendored.
  Verified live: `GET /api/users?search=&limit=` → `{"users":[…],"total":n}`; user objects carry
  `hwid_limit` (null = unlimited), `group_ids`, `note`, `on_hold_expire_duration`, `admin`.
- This server runs the **dev compose** (`docker-compose.yml`: runserver + Vite dev servers, `./backend`
  bind-mounted, so backend edits are live). Prod overrides: `docker-compose.prod.yml` (gunicorn + daphne for `/ws/`).
- `web` runs migrations on start (`RUN_MIGRATIONS=1`). **New bind mounts need `docker compose up -d web`**;
  a plain `restart` keeps the old mounts.
- Tests: `docker compose exec -T web python -m pytest -p no:warnings` (settings `config.settings.test`,
  **real MySQL** in the container). Browser checks: Playwright image `mcr.microsoft.com/playwright:v1.49.1-noble`
  against built SPAs with a mocked API (never create fake data in the prod DB).

## Conventions
- API-first under `/api/v1/`; admin API `/api/v1/admin/…` uses the **separate `Staff` model** + staff JWT +
  `StaffPermission`: `perms_map` per method, `action_perms` per viewset action (wins over `perms_map`).
- Every admin write that matters → `write_audit(action=…, staff=request.user, target=…)`.
- Panel operations: **panel first, then read the account back and mirror it** (`apply_user_to_service`);
  only send changed fields (`update_service`). Never delete a panel account when "disable" is meant.
- Users are **soft-deleted** only (`apps/accounts/deletion.py`); hard `DELETE /admin/users/<id>/` is 405
  (it would cascade orders/payments and change revenue). Deleted users are excluded from lists, stats,
  pickers, referral codes, scheduled renewals.
- Phones: always through `apps/accounts/phone.py` (`normalize_ir_phone` → `09xxxxxxxxx`); uniqueness is
  app-level. A Telegram contact that matches a site account merges the bot account into it
  (`telegram/accounts.py::link_telegram_phone`) and invalidates the unverified site password.
- JWT: `CHECK_REVOKE_TOKEN` + tolerant `apps.accounts.authentication.JWTAuthentication` (claim-less old
  tokens still accepted; unusable-password accounts rejected). Password change returns a fresh pair.
- Live updates: WebSocket `/ws/notifications/` (customer JWT) and `/ws/admin/payments/` (staff JWT +
  `payment.view`) via `apps/notifications/live.py::push_payments_event` (sent on commit).
- Frontend: fa/en for every string (per-page `T = {fa, en}` or `lib/i18n.jsx`), Jalali via `lib/format.js`,
  Persian digits via `digits()`. Themes: Caspian (light/dark), Midnight Aurora, Royal Frost. Colours come from
  `var(--c-*)` except these **fixed** tokens: toggles `--toggle-on #11AB53` / `--toggle-off` dark gray;
  ConfirmDialog tone colours (danger red, success #11AB53, primary #1464BA, warning amber).
- **One popup for everything**: `components/ConfirmDialog.jsx` (identical in both SPAs) + `useConfirm()`.
  Never use `window.confirm/alert/prompt`. **One copy helper**: `lib/clipboard.js::copyToClipboard`.
- Fonts are bundled (`@fontsource`, no CDN): fa = Vazirmatn, en = Inter, `<code>` = JetBrains Mono.
- Mobile (≤767px, Caspian admin): bottom nav + Settings page = index of every page not in the bottom nav.
  A new admin page must be reachable from the sidebar **and** that index.

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
- Media: only `/media/branding/` is public (served by Django on the dev-compose server, `DEBUG=False`);
  receipts and operator apps are private and only reachable through auth-checked API views.
- UI audits against the live server: the anonymous throttle is 60/min per IP (`/config/`, `/pages/`), and
  the SPAs are Vite dev servers — heavy parallel loads make both fail. Snapshot public endpoints and keep
  concurrency low; never switch the live active theme (intercept `/api/v1/theme/` instead).
- Tests that call `transaction.on_commit` work need `@pytest.mark.django_db(transaction=True)` and a stubbed
  `fulfill_order.delay` (no panel in tests). Bot handler tests must stub `close_old_connections`.

## Operator phone tools
- Android SMS Bridge: `mobile_sms/` (Kotlin); the APK in `mobile_sms/release/` is served by the panel.
- **iPhone Shortcut: single source `mobile_shortcut/CaspinSMS.shortcut`** (XML plist, no secrets; endpoint +
  token are import questions). The panel download builds it from that file and fills in the endpoint (and
  optionally one device's token) at request time; iOS files cannot be uploaded.
  **Shortcut change = update the repo file + panel download (automatic) + bump `mobile_shortcut/VERSION`
  + changelog in `mobile_shortcut/README.md`.** Keep the two action UUIDs the backend looks for.

## Secrets
- Nothing secret in git: `.env` (gitignored), device tokens, panel/bot credentials live in the DB
  (encrypted fields where sensitive). Grep the diff for tokens before every commit.
