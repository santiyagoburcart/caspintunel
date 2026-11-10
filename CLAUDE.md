# CLAUDE.md — working notes for caspintunel

Read `PROGRESS.md` first (build state, phase log, open items). This file holds
the **durable rules and gotchas**. Keep both short; don't duplicate them.

## Stack & layout
- Django 5.2 + DRF + Celery + Channels (Redis) + **MySQL 8 in prod** · React 18 + Vite + Tailwind SPAs:
  `frontend/user` at `/`, `frontend/admin` at `/panel/` (Vite `base:/panel/`).
- Panel = **PasarGuard over HTTP only** (v5.6.0 live as of 2026-11-04; was 5.4.1) (public schema: `<panel>/openapi.json` — read field lists from it, never from memory) (`apps/panel/client.py`), never vendored.
  Verified live: `GET /api/users?search=&limit=` → `{"users":[…],"total":n}`; user objects carry
  `hwid_limit` (null = unlimited), `group_ids`, `note`, `on_hold_expire_duration`, `admin`.
- **PRODUCTION = this Finland server** (host `ubuntu-4gb-hel1-2`, `46.62.192.189`), migrated
  from `66.245.203.63` on 2026-10-21 (`docs/migration.md`). Every command here touches the live site.
- **This server runs PROD** (`docker-compose.yml` + `docker-compose.prod.yml`; `.env` sets `COMPOSE_FILE`
  so plain `docker compose …` means prod): nginx → built SPAs, gunicorn (`web`), daphne (`/ws/`), celery
  worker/beat, both bots. Code is **baked into images** — a backend/frontend change is live only after
  `./update.sh` (backup → pull → build → one-off migrate/seed/collectstatic → **rolling** swap of web,
  daphne, both SPAs behind healthchecks → plain up for the rest). Migrations run while the previous release
  still serves: keep them backward compatible (add now, drop next release). Prod uses `volumes: !override` / `!reset` so none of the dev
  bind mounts leak in. The dev compose alone (`docker compose -f docker-compose.yml`, `./update.sh --dev`)
  is for development machines only (runserver + Vite, `./backend` bind-mounted).
- **Memory (v1.39.0)**: every prod container has a `mem_limit` (`docker-compose.prod.yml`, sized for 2 vCPU / 3.7 GiB —
  architecture.md#memory-limits-and-tuning-v1390). A new container gets one too. Never run an SPA build (~1 GB) while the test
  stack runs — the kernel OOM-kills it. Watch = Monitoring «حافظهٔ کانتینرها» (`apps/ops/containers.py`).
- `./update.sh` first dumps the DB to `backups/pre-update-<ver>-<ts>.sql.gz` and tags the running app images
  `:rollback`, then pulls/builds/ups. **Rollback: `./update.sh --rollback`** (images only; restore the dump
  if a migration must be undone). Build images only through `update.sh`: with the containerd image store a
  manual `docker compose build` drops the previous image, so there is nothing left to tag.
- **Local backup retention** (`apps/ops/retention.py`, hourly beat `prune_backups_task`, `manage.py cleanup_backups
  [--dry-run]`): DB backups are deleted after `backup_retention_days` (Settings → Backup, default 2) ONLY when
  `BackupLog.sent_to_telegram`; unsent ones are re-sent, else kept + alerted (backup chat, Monitoring); the newest
  2 always stay. Uploads > 50 MB go in parts. `pre-update-*` keep 3, `backups/migration/*` 7 days; Docker leftovers:
  `scripts/docker-cleanup.sh` (run by `update.sh`; keeps `:latest` + `:rollback`). Never delete an unsent backup.
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
  A deposit within ±20 % of an open invoice (or equal only after ×10/÷10) is linked to it (`SmsMessage.mismatch_order` +
  `less`/`more`) and gets a PENDING `sms_mismatch` payment for manual review (Payments queue, live `sms_mismatch` event).
  **The ONE exception = `payments_sms/rounded.py` (v1.32, widened v1.44.1, SMS + Blu):** a deposit within ±`rounded_max_toman`
  (default 2,000 T) of exactly ONE open invoice (order / agency payment), inside its window, not already used by another approved
  payment (exact or rounded — SMS + Blu copies). BELOW also needs a receipt or a known payer card; ABOVE needs none. Never with 2+
  candidates, never twice for one deposit; paid amount + signed `shortfall` (invoice − paid, negative = more) recorded; undo = void.
  Don't widen it elsewhere.
- **Manual invoices (v1.38, `orders/manual.py`)**: approved only through `approve_payment(confirmed_at=…)` (revenue on the
  entered date) or the normal checkout; never set a manual order / payment status by hand. Tag = `Order.manual_invoice`.
- **Renewal plans** (v1.42.1): `renewal_plans` = every active plan of the service's panel incl. custom volume; `plan_renews` decides
  (a retired plan only when `Plan.renewable_when_inactive`, and only for services already on it). Custom-volume renewals carry the
  bought bytes in `ScheduledRenewal.data_limit` → `renew_service(…, data_limit)`; `last_renewal_gb` pre-fills the GB.
- **One renewal per service at a time** (`orders.services.waiting_renewal`): no new renewal order while one is queued,
  paid or under receipt review, and `schedule_renewal` never replaces an unapplied `ScheduledRenewal` (→ order `failed`
  + staff alert). Incident 2026-10-29: one transfer paid two renewals. Queue warnings live in `payments_sms/checks.py`.
- Panel operations: **panel first, then read the account back and mirror it** (`apply_user_to_service`);
  only send changed fields (`update_service`). Never delete a panel account when "disable" is meant.
- Users are **soft-deleted** first (`apps/accounts/deletion.py`); hard `DELETE /admin/users/<id>/` is 405
  (it would cascade orders/payments and change revenue). Permanent delete = `apps/accounts/purge.py::purge_user` only
  (Super Admin + `users.purge`): anonymizes the row, never deletes it, never touches orders / payments. The daily auto-purge
  (`accounts/autopurge.py`, setting off by default) calls the same function — never a copy. Deleted users are excluded from lists, stats,
  pickers, referral codes, scheduled renewals.
- Phones: always through `apps/accounts/phone.py` (`normalize_ir_phone` → `09xxxxxxxxx`); uniqueness is
  app-level. Every Telegram contact goes through `telegram/accounts.py::handle_contact` (own contact only;
  with `force_share_phone` no account exists before it — bot and Mini App). A matching site account gets the
  Telegram link and **keeps its username, password and sessions** (never `set_unusable_password` — that locked
  out 3 customers, incident 2026-10-29); a number linked to another Telegram id is refused + staff alerted.
- Staff JWTs carry `tv` = `Staff.token_version`; always resolve the staff with
  `adminpanel.tokens.staff_for_payload()` (never a bare `Staff.objects.get(pk=payload[...])`). Password change or
  `manage.py revoke_staff_sessions [--username X]` ends staff sessions (customers untouched). Spent refresh
  jtis live in the DB (`StaffRevokedToken`), never only in Redis.
- JWT: `CHECK_REVOKE_TOKEN` + tolerant `apps.accounts.authentication.JWTAuthentication` (claim-less old
  tokens still accepted; unusable-password accounts rejected). Password change returns a fresh pair.
- **Sign-in endpoints never authenticate** (`apps/common/auth_reset.py::FreshAuthMixin`) and the SPAs never attach a
  stored token to them (`lib/api.js::isAuthCall`) — a staff token fails the customer JWT check, which kept operators out
  until they cleared storage (incident 2026-10-30). API = JWT only (no `SessionAuthentication`); Django-admin cookies are
  `ct_admin_sid` / `ct_admin_csrf` on Path `/admin/`. A new public auth endpoint gets the mixin + the SPA regex.
- Live updates: WebSocket `/ws/notifications/` (customer JWT) and `/ws/admin/payments/` (staff JWT +
  `payment.view`) via `apps/notifications/live.py::push_payments_event` (sent on commit).
- **Days are Tehran days** (server TZ is UTC): date filters / reports / cards use `apps/common/jalali.py` (`tehran_day_start/end`,
  `today_bounds`, `jalali_month_bounds`); never `make_aware(date)` or `TruncDate` without `tzinfo=TZ`. Transactions cards = `transactions/summary/`
  (the list's own query, `pay_date`) — never a separate rolling-window aggregate. **A date / time staff type without an offset
  is Tehran time** (`manual._parse_dt`, v1.42.1 incident: 12:22 today refused as "future"); SPAs send `+03:30` and default to
  Tehran "now"; "today" = `jalali.tehran_today()` (never `timezone.localdate()` / `date.today()`). Future check: 5 min skew.
- Frontend: fa/en for every string (per-page `T = {fa, en}` or `lib/i18n.jsx`), Jalali via `lib/format.js`.
  **Digits are always Latin 0-9** in both languages (amounts, dates `1405/07/03`, badges, %, bot text);
  every `fa` Intl formatter needs `-u-nu-latn`. Persian/Arabic digits are only normalized on INPUT
  (`user/src/lib/phone.js`, `accounts/phone.py`, `payments_sms/parsing.py`). Themes: Caspian (light/dark), Midnight Aurora, Royal Frost. Colours come from
  `var(--c-*)` except these **fixed** tokens: toggles `--toggle-on #11AB53` / `--toggle-off` dark gray;
  ConfirmDialog tone colours (danger red, success #11AB53, primary #1464BA, warning amber).
- **Every action gives feedback**: admin `lib/api.js` reports each POST/PUT/PATCH/DELETE to `components/FeedbackBridge.jsx`
  (toast success / real failure reason). The toast (`components/Toast.jsx`, identical in both SPAs) is the ONLY result
  display — no inline "saved" bars. Pass `{ quiet: true }` only for non-actions (login, live previews).
- **One popup for everything**: `components/ConfirmDialog.jsx` (identical in both SPAs) + `useConfirm()`.
  Never use `window.confirm/alert/prompt`. **One copy helper**: `lib/clipboard.js::copyToClipboard`.
  **One receipt picker**: `components/ReceiptDrop.jsx` (identical in both SPAs; type/size checks, preview, upload bar) —
  never a bare `<input type="file">` for a receipt.
- Fonts are bundled (`@fontsource`, no CDN): fa = Vazirmatn, en = Inter, `<code>` = JetBrains Mono.
- Mobile (≤767px, Caspian admin): **no ☰ / drawer** — bottom nav + Settings tab = index of EVERY page + account
  (profile, language, theme, logout); avatar opens it. Sidebar and index both come from `components/adminNav.js` — add a
  new admin page there (+ hub text, `MOBILE_TITLES`, `PAGE_API` in `test_mobile_nav.py`); a list permission = all of them.
  Phone density: record-grid cards (not stacked tables), KPI tiles 2 per row, subtitles hidden, inputs 16px,
  targets ≥44px. Badge/pill **text** uses `--c-*-fg` (contrast-safe); "expired" is always `muted` gray.
- Subscription QR = `apps/common/qrcard.py::qr_card_png` everywhere (bot, site modal, downloads): never
  restyle the code itself (black on white, 4-module quiet zone, integer modules); backgrounds are bundled
  JPEGs (`qr_backgrounds/generate.py`) or the Branding upload. Bot support IDs/text live in `SiteConfig`.
- Admin "Documentation" serves only `docs/*.md` (secret-looking `NAME=value` lines masked). Keep docs free
  of real values; new docs show up automatically.
  `docs/` is bind-mounted read-only into prod `web`, so a docs change is live on /panel/docs as soon as it is in the
  working tree (no deploy). Permissions table: architecture.md#permissions-rbac (regenerate from the DB when codes change).
- **Docs rule — every phase / release that changes models, services, Celery tasks, containers, host jobs or a
  user-visible flow updates `docs/architecture.md`, `docs/erd.md` (Mermaid ER + table list) and `docs/flows.md`
  (Mermaid sequence diagrams) in the same commit**, plus `docs/roadmap.md` when a planned phase starts or ships.
  Write only what the code does (check enum values / schedules in the code, never from memory).
- **Multi-tenant (v1.40+, docs/multi-tenant.md)**: every model is classified in `apps/tenancy/registry.py` (TENANT / NULLABLE /
  PLATFORM — a test fails on an unclassified model). A new tenant table gets `tenant = tenant_fk()` (`apps/tenancy/fields.py`;
  NOT NULL since v1.42 — `null=True` only for NULLABLE). A unique field on a tenant table is unique per store
  (`UniqueConstraint(fields=["tenant", …])`, never `unique=True`) and its serializer adds the "already exists" check
  (`adminpanel/serializers.py::per_store_unique`). A new data migration that creates tenant rows must set `tenant`.
  Since v1.41 (Release B) every TENANT model is scoped: the host picks the tenant (`apps/tenancy/middleware.py`), queries
  filter via the compile-time `tenant__tenant_scope` lookup, new rows get the current tenant. Background code runs in the
  default tenant for now; use `tenancy.context.tenant_context(id)` for another store. **Strict (v1.42, `TENANCY_STRICT`)**: in
  gunicorn a tenant-table query outside a request (thread, after the response) raises `NoTenant` — copy the context
  (`contextvars.copy_context().run`) into threads that query. `unscoped()` only in files listed in
  `context.ALLOWED_UNSCOPED` (test-enforced). The isolation sweep (`apps/tenancy/tests/test_isolation.py`) is a release gate.
  **Store mode (v1.43)**: on a store's domain an admin view answers only with `store_ok = True` (default-deny, Super Admin too) —
  add it only to views whose data is tenant-scoped and safe for a reseller; platform paths are 404 there
  (`tenancy/middleware.STORE_BLOCKED_PREFIXES`). Customer-facing branding = `settings_app.branding.branding()` (never
  `SiteConfig.load()` for what a customer sees); a store-settable key goes into `TENANT_KEYS`. The admin SPA's store menu is
  `adminNav.STORE_GROUPS` (+ store routes in App.jsx) — a page joins it only together with `store_ok` on its API; the user SPA
  never hard-codes our brand (names come from `/config/`).
  **Store domains (v1.45, `tenancy/domains.py`)**: only our staff add / change / remove them («فروشگاه», `agency.manage`). The app
  only writes `backups/.tenant-domains.json`; certificates + `nginx/tenants/<host>.conf` are made ONLY by the host watcher
  `scripts/tenants.sh` (cron; pre-check → HTTP-01 webroot → nginx -t → reload → TLS verify → rollback) — never edit those files
  by hand, never issue store certificates elsewhere. Lineage `store-<host>`; caspintunel.com's vhost must stay the first 443
  server (unknown names). `/.well-known/caspin/<token>` is answered before any host check (proves a host reaches us). Test the
  watcher only with `scripts/test-tenants.sh`.
  **Celery + stores (v1.46, `tenancy/celery_ctx.py`)**: a task queued inside a tenant context runs in it (header
  `caspin_tenant`); a periodic job that touches customer data loops with `context.for_each_tenant` (never just the default).
  A store's PasarGuard account = our token + `set_owner` to the reseller, read back (`panel.services._hand_to_owner`). Every
  store sale / renewal / add-on / manual invoice with a service action goes through `tenancy.quota.check` (agency numbers,
  never a new formula); store plans only through `tenancy.catalog.validate_plan` (agency panel, role groups).
  **Payments per store (v1.47)**: unique-amount pool = the store (`order_tenant_amount_lock`); agency payments are OUR pool only
  (empty in a store context — keep it so). SMS devices post to their store's domain. `alert_staff` / `push_to_staff` / the live
  payments socket follow the current store — pass `platform=True` only for alerts meant for US (quota, domains); never let a
  store's payment data reach our staff, backup chat or our live group. Blu stays ours (blocked on stores, no Blu data in a
  store's queue).
  **Store bots (v1.49, `tenancy/bots.py`)**: only our staff set a store's bot token (never our own bots, one store per bot,
  never returned / logged / audited). Telegram calls OUR host `/api/v1/telegram/hook/<id>/` (secret header); updates run the
  sales bot's handlers in Celery inside the store. `sales_client()` = the CURRENT store's bot (None without one) — use it for
  customer messages; `our_sales_client()` for anything meant for our staff / our bot. Staff flows never run in a store bot.
  **Store data stays in the store (v1.50)**: `Staff` is NULLABLE = NOT scoped — every staff loop for a store event filters
  `tenant_id=store_id()` (None = ours). Customer messages go through `notify_user` (delivers in the customer's store); links via
  `branding.public_base()` / `links.admin_link`, never `PUBLIC_BASE_URL` / `PROJECT_NAME` for a customer.
  **v1.51**: `set_setting` in a store writes ONLY its `TENANT_KEYS` (else `StoreSettingRefused`) — never bypass it with
  `Setting.objects`. A page joins `STORE_GROUPS` only when the reverse sweep (`test_phase7b.py`) stays green.
  **Store staff (v1.52, `tenancy/staff.py`)**: `Staff.tenant` set = a reseller's staff — sign-in / tokens only on that store's
  domains (`tokens.staff_for_payload`), `has_perm` capped by `Tenant.permission_ceiling` (⊆ `STORE_CODES`), never Super Admin.
  Roles / staff queries always filter `tenant_id=store_id()`. A new store_ok view's codes must be in `STORE_CODES` (test).
  **v1.52.1**: a store's «ساخت ناموفق» is retried only through `tenancy/failed_orders.retry` → `retry_provision` (same paid order,
  never a new charge), from the store panel or our «فروشگاه» card (inside the store's context).
  **v1.53 exports (`tenancy/export.py`)**: a store backup reads ONLY explicit field lists inside the store's context — a new
  dataset / field gets the same treatment (no hashes, tokens, our panel / staff names; cards masked); files only under
  `media/exports/` (nginx 404), served only through `consume` (one-time, host-bound link). **Fees (`tenancy/fees.py`)**: off by
  default; invoices only through the agency ledger / `issue_for_entry(kind=store_fee)`; suspension only by `run` and only when
  `suspend_enabled` — never suspend / resume a store elsewhere for a fee.
- The rejected Liquid Glass refresh is archived at tag `archive/ui-refresh-liquid-glass` — don't copy from it.

## Gotchas (learned the hard way)
- `useEffect(load, [])` where `load` returns a Promise breaks under StrictMode (dev server). Always
  `useEffect(() => { load() }, [])`.
- **Two migrations with the same name** from different sessions: Django trusts the name, not the schema.
  After merging someone else's migrations, compare real columns with the models (`accounts.0008` exists
  because an unmerged `0006` draft had been applied to this DB).
- Mermaid sequence diagrams: a `;` inside a message ends the statement and the whole diagram fails to parse (the panel then
  shows its source) — write `·` instead. 10 flows were broken this way until v1.38.4.
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
- Test settings switch DRF throttles OFF. A custom `request.user` (e.g. the agency `Reseller`) must have a `pk` or
  `UserRateThrottle` 500s in production only; test such endpoints with the production throttle classes.
- Tests that call `transaction.on_commit` work need `@pytest.mark.django_db(transaction=True)` and a stubbed
  `fulfill_order.delay` (no panel in tests). Bot handler tests must stub `close_old_connections`.

## Agency panel (apps/agency, docs/agency.md)
- 1:1 port of PAMP v1.5.3 (reseller admins). Formulas, sync order and enforcement are VERBATIM (PORTING.md);
  `tests/test_golden.py` compares them with the ORIGINAL PAMP code — never "improve" them here.
- Cut-over done 2026-10-16: sync (`agency_sync_interval_minutes`, production 2 min) + enforcement + portal are ON here; the Finland PAMP has its workers
  stopped. Never run two syncs on one panel (rollback steps in docs/agency.md). Resellers are NOT `accounts.User` rows.
- Real PAMP data (dumps, recorded panel responses) lives only in `backups/pamp/` and `backend/.golden_local/`.
- v1.52.2: every limit change through our panel calls `agency/release.release_if_room` after PasarGuard accepted it (ends a
  `pamp_blocked` block at once when there is room) — a new limit-changing path must call it too; never edit enforcement for it.
- PasarGuard admin create / edit / delete = `apps/agency/admin_crud.py` on `PasarGuardClient` (never edit the PAMP files
  for it). 5.4 has roles, not `is_sudo`. Passwords are returned once to the UI and never audited / stored.

## Tickets (apps/tickets, docs/architecture.md#ticketing)
- Every state change goes through `tickets/services.py` (event + audit + `notify.queue` on commit) — never edit
  `Ticket.status` directly. The active-service gate and open-ticket limit are enforced there, not in the UI.
- Staff ticket endpoints always start from `rules.staff_queryset(staff)` (topic scope; out of scope = 404).
  No scope rows = all topics; superadmin = all. Customers never see internal notes or staff names.
- Attachments: `rules.check_attachments` (sniffed type + Pillow decode, ≤ 3 × 5 MB), random file names under
  `media/tickets/` (nginx 404s it), served by `AttachmentFileView` only. A new private media folder needs the
  same nginx rule in `nginx/prod.conf` + `nginx/conf.d/caspintunel.conf`.
- Staff Telegram link = `/start staff-<CODE>` in the sales bot, handled before `ensure_bot_user`.
- Topic gate = `rules.has_any_service` (EVER had a service); `renew_hint` only drives the "expired — renew" hint.
- Bot: customer flows `tk:*`, staff flows `st:*` (`apps/tickets/bot.py`). Staff callbacks / typed `st_reply` are handled
  BEFORE `_user()` in `sales_bot` (no customer account, no customer gate). Live customer updates go over the
  existing `/ws/notifications/` socket (`ticket.event`; the bell re-emits it as the `ct:ticket` window event).

## CRM (apps/crm, docs/architecture.md#crm)
- Stage / detection / case rules live in `crm/services.py`; every change writes a `CrmEvent` (timeline). Detection only
  trusts services synced in the last 24 h. Staff-opened tickets go through `tickets.services.open_for_user`.
- Messages to customers always via `notify_user` (site / bot / email); templates use `{name} {username} {service} {site} {guide}`.
- Analytics (`crm/analytics.py`) is read-only: revenue = approved payments by confirmed_at (same as Accounting); never write
  from it and never change payment / agency / ledger calculations for a report.
- Retention (`crm/retention.py`): warnings are unique per (service, kind, threshold, period_key) — never send one outside
  `run_warnings` / `deliver_pending`; channels are tracked per warning (quiet hours). The old `ops.alerts` only runs when
  `retention_warnings_enabled` is off. Discount codes: `create_order(discount_code=…)` → `retention.check_code`; used on paid.

## Paths (docs/paths.md)
- The admin SPA must work under ANY base: build with relative assets, never hard-code `/panel` (use `lib/base.js`
  ADMIN_BASE); the user site gets the portal path / admin link from nginx-injected metas (`lib/paths.js`).
- nginx routing for both lives in the generated `nginx/paths/active.conf` (template + `render-paths.sh`); changes go
  through `scripts/paths.sh` (nginx -t, reload, verify, rollback). Never edit active.conf by hand.

## Access mode (docs/access-mode.md)
- Direct / Cloudflare proxy / Iran tunnel change only `@` and `www` A records — never `mail.*`. Switch only through the
  panel / `settings_app.access` (verify → DNS → verify → revert). Never hard-code tunnel IPs, sources or ports; never
  trust CF-Connecting-IP outside Cloudflare's ranges or a client-sent X-Conn-Addr. The certbot Cloudflare credentials
  (`nginx/letsencrypt/cloudflare.ini`, 0600) never go to `backups/` or git.

## SMS ingest (docs/sms-batch.md)
- SMS are matched at `received_at` (when the phone got them) via `matching.open_orders_at`; keep `inbound-batch`
  idempotent (`dedupe_key` unique) — never match or approve an SMS twice. The old `/inbound/` stays for the Android app.
- Blu deposits (docs/blu-webhook.md): signature checked on the RAW body before parsing; `bank_id` unique, existing rows never
  touched; matched once, in Celery, only inside the order's window (`created_at − 2 min … unique_expire_at + grace`) — unique
  amounts are reused. Card numbers stay masked (first6******last4), also in `raw`. The secret is only in `.env`.
  Collector health = `blu_service.py`: ONE fixed read-only SSH command (is-active + journal); never add other remote
  commands there. The key is mounted read-only into `celery_worker` only. Stale threshold / late grace / SSH interval are
  Super Admin `setting` rows (win over `.env`); `/admin/settings/` keys in `SUPER_ONLY` are 403 for everyone else.
  Liveness = last successful poll ("poll ok" journal line), session/login/OTP errors, service state — NEVER "no deposit
  for N minutes" (a quiet account is not an outage; that alert fired nightly and was removed in v1.33.1).
  **Linking (v1.42.2, `payments_sms/blu_link.py`)**: a deposit for an ALREADY approved payment is only `linked` (identification,
  never a second approval or count); unpaid targets are approved through `confirm_blu` / agency `approve_payment` only.
  Auto-link = `signals.py` (same reference, else ONE same-amount deposit in 24 h + payer name); unlink = Super Admin, link-only
  rows only. A new match note needs its Persian rule in `blu_notes.py`.

## Agency invoices / payments (v1.34, docs/agency.md#invoices-and-payments-v134)
- Every agency charge goes through `ledger.record_quota_charge` / `add_entry` → `billing.issue_for_entry`; no price per GB
  = no charge (`billing.ensure_price` BEFORE touching PasarGuard). Never record a 0-amount charge again.
- Agency payments are `AgencyPayment`, never `payments_sms.Payment`: keep them out of customer revenue, Transactions,
  Analytics and the customer queue. Their unique amounts share the order pool (`agency_locked_amounts` ↔ `customer_locked`).
- One payer per admin (`billing.payer_for`): the group manager if the admin's group has one, else the admin. Portal access
  = `billing.portal_access` (owner of managed group blocked, sub-admins read-only, `AgencyAdminSetting` override).
- v1.35.1: invoices are settled ONLY through `allocation.py` rows (never set `AgencyInvoice.status` to paid by hand):
  ledger payment / «کاهش بدهی» → `apply_entry`, checkout → `allocate_agency_payment`, «تسویه خارج از سیستم» → `settle_outside`.
  Invariant (`enforce`, after every entry / void / invoice): open invoices ≤ max(0, ledger balance).
- v1.38.2 /agency/ portal: sections + menu; bell / notifications page / stats tooltips are the SHARED files `AgencyBell.jsx`,
  `AgencyStats.jsx` (identical in both SPAs — edit both). Portal «پرداخت کل بدهی» = `billing.pay_all(None, names, expected, admin=…)`;
  invoice labels use `invoice_row.source`, not the kind alone.
- v1.37 group-manager panel: lists page on the SERVER (admins 20, activity 30, notices 20) — never filter / search only the
  loaded page. Manager notices = `billing.notice(manager=…)` (DB + push); the UI shows them only in the header bell / page.
- v1.36: group managers' reseller numbers = `manager_views._admin_row(full=…)` over `api.admin_row` (never re-derive a formula
  in the manager code); live counts only through `live_stats` (read-only GETs, cached).
- v1.35.3: admin text fields that become subscription headers (profile_title, support_url, …) are saved ONLY through
  `admin_crud.build_payload` → `clean_field` (invisible / control characters broke Happ, 2026-11-03). Never PUT raw input.
- v1.35.2 group debt = `billing.debt_breakdown` only (manager page + staff group card); «پرداخت کل بدهی» = `billing.pay_all`
  (re-checks the total under lock, 409 `total_changed`) — never charge a total the payer did not see.
- SMS / Blu: customer orders are matched first, agency payments after (`billing.match_deposit`, `near`, rounded
  candidates); a deposit equal to both is held for review (`hold_ambiguous`).

## Panel account names
- Never attach a customer to a panel account we did not create: names are checked in our DB **and** on the panel
  (`orders.services.check_account_name`); a 409 on create is adopted only for our own earlier attempt (note
  `caspintunel#<service id>`, not older than the service) — otherwise `PanelNameTaken` → the order waits for a new
  name (`needs_new_name`). Linking an existing account is an explicit staff action; another admin's account needs
  `confirm_other_admin`.
- **Format = PasarGuard's username rule, ONE module** (v1.42.1): `apps/panel/account_names.py` (3–64 of `A-Za-z0-9_.@-`, no two
  symbols in a row; `suggest()` = the fixed name) + `lib/accountName.js` / `components/AccountNameInput.jsx` (identical in both
  SPAs). Every name form uses them and `create_order` re-checks before payment (`clean_account_name` → `AccountNameRefused`).
  Never add another regex for account names. Incident 2026-11-06: bot accepted «sahar 1364», 422 after payment.
- **«ساخت ناموفق»** (v1.42.1): a paid order PasarGuard refuses gets `provision_error` / `provision_failed_at` in
  `orders/tasks._provision_failed` — staff alerted once, customer told «در حال آماده‌سازی», `retry_unfulfilled_orders` skips it;
  only staff `retry_provision` (Transactions detail) clears it. A never-created service of a paid order is never synced to «disabled».

## Domain (docs/domain.md)
- The site domain changes only through the wizard / `scripts/domain.sh` (certificate check, nginx -t, .env, rolling
  restart, verify over TLS, rollback). Never edit `nginx/domain/active.conf` or the domain keys of `.env` by hand while a
  change is in progress; recovery: `./scripts/domain.sh show | rollback`. Test only with `scripts/test-domain.sh`.
- Mail moves with the domain (DKIM made by the mail server, MX/SPF/DMARC/DKIM via Cloudflare, `MAIL_DOMAIN`, mail cert);
  only the PTR is manual. Never copy DKIM private keys out of `mail/config/opendkim`.
- The Cloudflare token is write-only (encrypted `DomainConfig.cloudflare_token`, never in an API response or log).
- `www.<domain>` only redirects (301 / 308 → `https://<domain>$request_uri`, rendered by `domain.sh render`, kept by
  every access-mode re-render, checked by `verify`); never serve the site on `www` again (separate browser storage).
- Wizard errors go through `settings_app/domain_errors.py` (`DomainError(key, …)` / `E.cloudflare` / `E.host`): fa + en
  text with the fix, raw code + message kept in `raw` for the page's "details" line. Add a key there, not a bare string.

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

## Notifications (v1.33, docs/architecture.md#notifications-telegram-sound-browser-push-v133)
- Staff alerts: always `alert_staff` (DM by permission, backup-chat fallback); ring by default, `silent=True` only
  for low priority. Agency events: `agency/notify.py` (buttons `ag:*`, same permission checks + `managers.approve/reject`
  as the panel). Never add notification calls inside the verbatim PAMP enforcement (`agency/tasks.py`).
- Web Push worker `push-sw.js` must stay notification-only (no fetch handler, no caches, scope `<base>push-sw/`);
  the user SPA's v1.28 cleanup unregisters every other worker. VAPID keys only in `.env`.
- "Needs action" counts come from `lib/actionCounts.js` — counts, never dots.

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
