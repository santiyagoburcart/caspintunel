# PROGRESS — caspintunel

> Single source of truth for build state. On any new/resumed session: **read this file first and continue from the first unchecked step. Do not rebuild completed work.**
> Stack: Django + DRF + Celery + Redis + MySQL + phpMyAdmin + Nginx + Docker · API-First (`/api/v1/`, JWT) · Jalali · fa/en
> References: `architecture.md`, `data-model.md`, `erd.mermaid`, `build-spec.md`

## Locked build decisions
- Frontend (user site + admin panel): **React + Vite + Tailwind** — two SPAs against the API
- Android SMS app: **Native Kotlin**
- Server IP: **66.245.202.46** · Active domain: **aicaspin.ir** (was caspin.skin — Cloudflare ToS hold)
- Panel: host `https://pas.hunaex.shop` — it's **PasarGuard API v5.3.0** (Marzban lineage), *not* Marzneshin. Token `POST /api/admin/token` (form), users under `/api/user`, groups (not "services"), user `status` field carries on_hold. `/openapi.json` is the source of truth.
- Django 5.2 LTS · Python 3.12 in container

## Global rules (always in force)
- No real secret/token ever hardcoded or committed — all in `.env` (gitignored) + `.env.example` (empty values)
- Sensitive DB fields (panel password, tokens) encrypted via `FIELD_ENCRYPTION_KEY`
- Email/Telegram failures are caught and logged — the system never crashes on an outage
- After each phase: run tests, write a summary here, **stop and wait for approval** before the next phase

> Phase numbering follows the user's phase prompts. Phases 1–2 are done and locked
> to the prompts given. Phases 3–11 below are a **tentative roadmap** (business logic
> per domain) and get confirmed / adjusted as each phase prompt arrives.

---

## Phase 0 — Understanding & planning  ✅
- [x] Read the 4 reference files
- [x] Create `PROGRESS.md`
- [x] Presented understanding of architecture + data model

## Phase 1 — Project skeleton & Docker  ✅
- [x] Folder structure per build-spec §3.2 (`backend/`, `frontend/`, `mobile_sms/`, `nginx/`, `docs/`, `db/init/`)
- [x] `docker-compose.yml` + `docker-compose.prod.yml` — services: web, nginx, db, phpmyadmin, redis, celery_worker, celery_beat (bot_sales / bot_backup stubbed, enabled in phase 9)
- [x] `.env.example` (build-spec §3.3, extended), `.gitignore`, `VERSION` (0.1.0)
- [x] Django `config/` project: settings split (base/dev/prod), MySQL, Redis cache, Celery + django-celery-beat, DRF, SimpleJWT, drf-spectacular (Swagger + ReDoc), configurable CORS/CSRF
- [x] `apps/common`: `EncryptedTextField`/`EncryptedCharField` (Fernet via `FIELD_ENCRYPTION_KEY`), Jalali helpers (`jdatetime`), `TimeStampedModel`, `AuditLog` + `write_audit()`, DRF throttle scopes (`auth`/`receipt`/`sms_ingest`)
- [x] 9 domain apps registered as empty packages (accounts, panel, plans, orders, payments_sms, notifications, telegram, settings_app, ops)
- [x] `install.sh` (interactive one-click: generates SECRET_KEY + Fernet key, writes `.env`, builds, migrates, creates superuser) + `update.sh` (git pull → rebuild → migrate → collectstatic)
- [x] `README.md`, `LICENSE` (Proprietary), `frontend/`+`mobile_sms/`+`docs/` placeholders
- [x] Verified: image builds, `manage.py check` clean, migrations apply, **8/8 pytest pass**, `/api/v1/`, `/api/v1/health/`, `/api/docs/`, `/api/schema/`, `/admin/` all reachable through Nginx; Celery worker responds to ping; prod compose config validates

## Phase 2 — Data models (all apps)  ✅
- [x] `apps.accounts`: custom `User` (`AUTH_USER_MODEL`, `db_table=user`, all data-model fields, auto 6-char `referral_code`, `referred_by`, `referral_count`), independent RBAC — `Permission` / `Role` (M2M `role_permission`) / `Staff` (own password hash + `has_perm(code)`, `is_superadmin` bypass)
- [x] `apps.panel`: `Panel` (`admin_password_enc` + `token_cache` = `EncryptedTextField`), `Service` (on_hold_duration/on_hold_timeout, expire_strategy, data_limit/used, device_limit, online_at, alert flags, FK current_plan)
- [x] `apps.plans`: `Plan` (fixed / custom_volume, nullable data_limit/duration_days/device_limit, price, discount_percent, min/max_gb, price_per_gb, `final_price`)
- [x] `apps.orders`: `Order` (type new/renew/addon_volume, amount + amount_unique, `unique_expire_at`, status). Partial-unique-on-active-`amount_unique` implemented via nullable-unique `amount_unique_lock` mirror (MySQL has no partial index) + `sync_unique_lock()`
- [x] `apps.payments_sms`: `BankCard`, `SmsSource`, `SmsAppDevice` (auto `api_token`), `SmsMessage` (raw_text, parsed_amount, matched_order), `Payment` (OneToOne order, `bank_card_id`, method card_manual/sms_auto/gateway, receipt ImageField, `confirmed_by` admin/system + `confirmed_by_staff`)
- [x] `apps.notifications`: `Notification` (broadcast/event, target_user null=broadcast, via_site/bot/email), `NotificationDelivery` (channel, status sent/failed/read)
- [x] `apps.telegram`: `TelegramConfig` (sales/backup, `token`=`EncryptedTextField`, proxy_url, backup_chat_id), `RequiredChannel`, `TelegramStats`
- [x] `apps.settings_app`: `Setting` (typed key/value + `.typed`), `SiteConfig` (singleton, branding + logo/favicon), `Theme` (JSON palette, single-active), `Page` (rules/tutorial/faq CMS)
- [x] `apps.ops`: `BackupLog`, `HealthCheck` (9 targets), `ResourceStat` (cpu/ram/disk/net/bandwidth); audit log reused from `apps.common`
- [x] All sensitive fields encrypted (`Panel.admin_password_enc`, `Panel.token_cache`, `TelegramConfig.token`) — verified ciphertext at rest in a test
- [x] `django-admin` registrations for every model
- [x] `manage.py seed` — idempotent: 15 permissions, Super Admin + Support roles, Midnight Aurora theme (palette from build-spec §4.2, active), SiteConfig singleton, 10 settings defaults + `active_theme_id`, 3 CMS pages, 2 telegram bot rows, Panel row from env (password encrypted). Wired into `install.sh` and `entrypoint.sh` (`SEED=1`)
- [x] `bot_sales` / `bot_backup` compose services now real (stub management commands until phase 9) — topology matches build-spec §3.1
- [x] Verified: 10 initial migrations apply on MySQL, `makemigrations --check` clean (no drift), `check --deploy` clean, **18/18 pytest pass**, seed idempotent across 2 runs, superuser creation works, OpenAPI schema generates, full 9-container stack boots

## Phase 3 — Auth & users  ✅
- [x] `POST /api/v1/auth/register/` — username/password/email/name/phone/referral_code; validates referrer code (→ `referred_by`), auto 6-char `referral_code`, returns JWT pair + `email_status`
- [x] `POST /auth/login/` (JWT, returns profile + rejects disabled), `POST /auth/token/refresh/`, `POST /auth/logout/` (blacklists refresh — `token_blacklist` app; `ROTATE`+`BLACKLIST_AFTER_ROTATION`)
- [x] `GET/PATCH /auth/me/` (profile; changing email clears `email_verified` + re-dispatches)
- [x] `POST /auth/password/change/` (auth, checks current)
- [x] Email verification (flowchart 1.1): gated by `email_verification_required` setting; `dispatch_verification()` → `skipped` / `sent` / `not_sent` (SMTP outage) / `no_email`; account always active; signed token (`django.core.signing`, 48h); `POST /auth/email/verify/resend/` + `/confirm/`
- [x] Password reset (flowchart 1.6): `POST /auth/password/reset/` email path — generic response (no user enumeration), `email_sent` bool + `alternative_paths` (telegram_bot / contact_admin) when SMTP down; `/reset/confirm/` with fingerprinted signed token (2h, invalidated by password change); `services.set_password_via_bot()` + `set_password_by_admin()` for the other two paths
- [x] Legacy import: `POST /auth/legacy/import/` (admin only) + `python manage.py import_legacy <file.json> [--overwrite]`; `is_legacy=True`, passwordless rows get an unusable password (must use a reset path); users with a supplied password can log in immediately
- [x] Rate limiting: `throttle_scope="auth"` (10/min) on register / login / reset / verify; `receipt` + `sms_ingest` scopes reserved for later phases
- [x] `apps/settings_app/utils.py` — `get_setting()` / `set_setting()` with outage-safe fallback
- [x] Test settings module `config.settings.test` (no throttle, locmem cache, dummy email, MD5 hasher) wired via `--ds` in `pytest.ini`
- [x] Verified: **35/35 pytest**, no migration drift, `check --deploy` clean, OpenAPI schema exposes all 11 auth paths, full live smoke test (register → login → me → reset) through Nginx

## Phase 4 — Panel connection & services  ✅
- [x] `apps/panel/client.py` `PasarGuardClient`: admin token via `POST /api/admin/token`, cached in `Panel.token_cache` (encrypted) + `token_expires_at`, auto-refresh, one silent re-auth on 401; typed errors (`exceptions.py`: `PanelUnavailable` [retryable — network/timeout/5xx], `PanelAuthError`, `PanelNotFound`, `PanelConflict`, `PanelValidationError`)
- [x] CRUD: `create_user` / `get_user` / `update_user` / `delete_user` / `reset_user_usage` / `set_user_disabled` / `get_user_usage`; monitoring: `system_stats` (`/api/system`), `system_resources`, `list_nodes`, `list_groups`, `list_expired_users`
- [x] `mappers.py`: `build_create_payload` (timed plan → `status:"on_hold"` + `on_hold_expire_duration` = the On-Hold strategy; timeless → `status:"active"`, `expire:null`; `group_ids` from `Panel.default_group_ids`), `build_renew_payload` (flowchart 1.5 — extends from current `expire_at`, new `data_limit`), `apply_user_to_service` (pulls status/used_traffic/expire[ISO or unix]/online_at/on_hold_* back; derives `expire_strategy`)
- [x] `services.py` (all idempotent / transactional, `select_for_update`): `provision_service` (adopts existing panel user on 409), `renew_service` (PUT same username + reset usage, keeps `subscription_url`, clears alert flags), `reset_service_usage`, `sync_service` (missing panel user → `disabled`)
- [x] `tasks.py` Celery: `provision_service_task` / `renew_service_task` / `sync_service_task` — `autoretry_for=(PanelUnavailable,)`, exp backoff, max 6, `acks_late`; permanent `PanelError` → `service.provision_failed` audit + admin flag. `sync_all_services` beat task fans out per live service
- [x] `Panel` model: `+default_group_ids`, `+subscription_base_url`, `+verify_ssl`; `Service` `+last_synced_at`. Migration `0002_panel_pasarguard_fields`
- [x] `seed` registers the `panel: sync all services` `PeriodicTask` (interval = `PANEL_SYNC_INTERVAL_MINUTES`, default 15) for the DB beat scheduler
- [x] Multi-username: unchanged `Service` model already gives one user → many panel usernames; every panel op keys on `Service.id`
- [x] `python manage.py panel_check` — probes the live panel
- [x] Verified against the **real panel**: auth OK, system stats (v5.3.0, 5827 users), 21 nodes `connected`, 4 groups listed (ids 5/6/8/10). **51/51 pytest** (client: token cache / 401 re-auth / 404 / 5xx→unavailable; mapping: on_hold / timeless / renew; provisioning: create+subscription / 409-adopt / renew-resets-usage / sync-missing→disabled / usage+online / unix-ts expire; tasks: fan-out / skip-without-panel). No drift, `check --deploy` clean

## Pre-Phase-5 — panel group assignment is admin-configurable  ✅
- [x] `apps/panel/constants.py` — `ALL_PANEL_GROUP_IDS = [5, 6, 8, 10]` (the live panel's current groups) + `default_group_ids()` callable
- [x] `Plan.group_ids` (JSONField, default = all 4 ids) — each plan defines which panel groups its service attaches to
- [x] `Panel.default_group_ids` default changed to the same 4 ids; migration `0003` backfills any existing panel row that had `[]`
- [x] `mappers.resolve_group_ids(plan, panel)` — plan's `group_ids` win, else fall back to `panel.default_group_ids`; used in `build_create_payload`
- [x] Plan admin: `PlanAdminForm` with a `CheckboxSelectMultiple` for `group_ids`, choices from the live panel (`/api/groups`, cached 5 min) with a static fallback + preserves ids no longer on the panel
- [x] Tests: created panel user gets the plan's `group_ids`; empty plan `group_ids` falls back to panel default

## Phase 5 — Plans, orders & payments (card-to-card)  ✅
- [x] **Plans API** `/api/v1/plans/` — `PlanViewSet`: public list/retrieve (active only), admin (`is_staff`) full CRUD; custom-volume validation; `Plan.price_for_volume(gb)` / `data_limit_for_volume(gb)` (discount + `ROUND_HALF_UP`)
- [x] **Orders** `/api/v1/orders/` — `create_order()` (flowchart 1.2): validates plan / account-name / custom-volume range / owned service; **atomic unique-amount allocation** — shuffled surcharge in `[unique_amount_min, unique_amount_max]`, retries on `IntegrityError` against the `amount_unique_lock` UNIQUE constraint; `unique_expire_at = now + unique_amount_reservation_minutes`. `expire_stale_reservations()` skips orders with a pending receipt. `OrderStatus.EXPIRED` added. Create response returns `payment_instructions` (amount_to_pay + reserved_until + active cards)
- [x] **Card-to-card** (flowchart 1.3): `GET /payments/cards/`, `POST /payments/receipt/` (`receipt` throttle, `ImageField`, `update_or_create` → pending), admin `GET /payments/pending/`, `POST /payments/{id}/approve/` (→ `confirmed_by=admin`, `confirmed_at`, `bank_card`; order → `paid`; enqueues fulfillment `on_commit`), `POST /payments/{id}/reject/` (reason; order stays open for re-upload)
- [x] **Fulfillment** `apps/orders/tasks.py::fulfill_order` — retry-safe (`autoretry_for=(PanelUnavailable,)`, backoff, max 6): new → create `Service` + `provision_service`; renew → `renew_service` (flowchart 1.5); addon → `add_service_data_limit`. Success → order `completed`, lock released; permanent `PanelError` → audit + admin flag
- [x] **Services + QR** `/api/v1/services/` — owner-scoped list/retrieve; `GET /services/{id}/qr/` → PNG of `subscription_url` (`qrcode`); serializer exposes `days_left` / `data_left` / absolute `qr` url
- [x] `seed` registers the `orders: expire stale reservations` beat task (every 5 min)
- [x] Migrations `plans/0002_plan_group_ids`, `panel/0003_alter_panel_default_group_ids`, `orders/0002_alter_order_status`. drf-spectacular warnings cleared
- [x] Verified: **74/74 pytest**, no drift, `check --deploy` clean, live smoke through Nginx (admin creates plan → buyer creates order [surcharge 1259, 30-min reservation] → uploads real PNG receipt → admin pending queue). Approve→provision path is mocked-tests only — **not run against the production panel**

## Phase 6 — SMS auto-confirm (flowchart 1.4)  ✅
- [x] `SmsDeviceAuthentication` (DRF) — `X-Device-Token` (or `Authorization: Device <token>`) → active `SmsAppDevice`; `request.user` stays an `AnonymousUser`, device on `request.auth`; bumps `last_seen_at`; `IsSmsDevice` permission; drf-spectacular security scheme registered
- [x] `parsing.py` — `normalize_digits` (Persian/Arabic-Indic → ASCII), `extract_numbers` (comma/٬/، grouping, strips trailing `.dd`, 4–12 digit guard), `candidate_amounts` (each number **and** number÷10 for rial→toman)
- [x] `matching.py` — `ingest_sms()` stores every `SmsMessage`; `_resolve_source()` treats active `sms_source` rows as a sender allow-list (last-10-digits match); `match_sms_message()` finds a `PENDING_PAYMENT` order whose `amount_unique_lock ∈ candidates` (`select_for_update`, oldest first); `_auto_confirm()` → `Payment(method=sms_auto, status=approved, confirmed_by=system, sms_message=…)` + `mark_paid_and_fulfill()` + audit
- [x] `POST /api/v1/payments/sms/inbound/` (`sms_ingest` throttle) — body `{text, sender?, received_at?}` → `{message_id, matched, order_id?, reason?}`; `GET /api/v1/payments/sms/ping/` heartbeat
- [x] `SmsAppDevice` admin: "regenerate token" action
- [x] No new migrations (models existed since Phase 2)
- [x] Verified: **83/83 pytest** (+9: digit/rial parsing, device-token auth 401s, ping heartbeat, match→auto-confirm→provision [mocked], non-match stored, no double-confirm on repeat SMS, sender allow-list reject/accept), no drift, `check --deploy` clean, schema clean, live smoke (ping + non-matching inbound through Nginx). Match→provision path is mocked-tests only — **not run against the production panel**

## Phase 7 — Telegram bots  ✅
- [x] `client.py` `TelegramClient` — raw Bot API over `requests`, per-bot proxy, `TelegramError`; `send_message` / `send_photo` / `send_document` / `get_chat_member` / `is_member` (swallows errors) / `get_me`
- [x] `config.py` — resolves a `TelegramConfig` (token decrypted by the field) → `sales_client()` / `backup_client()`; proxy from the row or `TELEGRAM_PROXY_URL`. Independent per bot — a Telegram outage never touches site/panel
- [x] `accounts.py` `ensure_bot_user()` — **first-time bot user → random `tg_xxxx` username + password** (returned once), `source=bot`, `telegram_id` link; returning users synced (username/phone/name), never recreated. `link_phone()` captures the Telegram phone on first share
- [x] `gate.py` (flowchart 1.7) — `check_access()` → `missing_channel_memberships()` (only when `force_channel_join`, per active `RequiredChannel`, via `is_member`) + `needs_phone()` (`force_share_phone` & no phone). Unconfigured bot = conservative (treat as missing)
- [x] `shop.py` — `buy_new` / `renew` (thin wrappers over `apps.orders.services.create_order`, `source="bot"`), `active_plans`, `user_services`, Persian formatters (`plan_label`, `service_summary`, `payment_instructions`, `delivery_message`)
- [x] `bot/sales_bot.py` + `bot/keyboards.py` — pyTelegramBotAPI (sync, pairs with Django ORM). Inline-keyboard menu: 🛒 buy (fixed → ask account name; custom_volume → ask GB) → payment instructions + "check status"; 📦 my services → detail → QR photo / renew; gate enforced on every interaction; contact handler → `link_phone`; per-update try/except so one bad update never kills the bot
- [x] `backup.py` `run_database_backup()` (build-spec 1.8) — `mysqldump --single-transaction --skip-ssl-verify-server-cert` → gzip → `BackupLog(ok)` → send via **backup bot** to `backup_chat_id`; dump failure → `BackupLog(failed)`, send failure → logged on the entry — **never raises**
- [x] `run_sales_bot` / `run_backup_bot` commands rewritten — real long-polling with restart-on-error; **idle (no crash-loop) until a token is configured**. Backup bot answers `/id` (chat id) and `/backup`
- [x] `tasks.py` — `run_backup_task` (beat, interval = `backup_interval_minutes`), `sync_required_channels_task` (beat, hourly, member counts). `seed` registers both + seeds `TelegramConfig` from `BOT_*` env
- [x] Compose: all backend services share `image: caspintunel-backend` (one build); `backups_data` volume on worker + bot_backup; Dockerfile adds `default-mysql-client` + `gzip`
- [x] Verified: **104/104 pytest** (+21: bot-user create/sync, phone link, gate matrix, TelegramClient send/member/errors, shop order creation + formatting, backup ok/sent/no-bot/dump-fail/send-fail, task summaries), no drift, `check --deploy` + schema clean, full 9-container stack boots with bots idling cleanly, **real `mysqldump` backup produced a 13 KB gz + `BackupLog(ok)`**

## Phase 8 — Admin panel API + branding + stats  ✅
- [x] **Staff auth (own RBAC)** — `apps/adminpanel/`: HS256 JWTs for the separate `Staff` model (`tokens.py`, claim `type=staff_access/staff_refresh`), `StaffJWTAuthentication`, `StaffPermission` (per-view `perms_map`/`required_perms`, superadmin bypass, **Django-superuser break-glass** via normal JWT/session). `Staff` gets `is_authenticated`/`is_anonymous` shims. `POST /api/v1/admin/auth/login|refresh/`, `GET /auth/me/`. `seed` bootstraps a `Staff` (Super Admin) from `DJANGO_SUPERUSER_*`
- [x] **Users** `/admin/users/` — filter (`is_active`/`source`/`language`/`is_legacy`/`email_verified`) + search + ordering, create, update, `set-password`, `enable`/`disable`, `legacy-import`; `service_count` annotation (`referral_count` from the model property)
- [x] **Plans** `/admin/plans/` full CRUD (RBAC `plans.manage`)
- [x] **Bank cards** `/admin/cards/` CRUD + **`/admin/cards/deposit-report/`** = Σ approved `payment.amount` and count per card + `grand_total`
- [x] **Transactions** `/admin/transactions/` — list/retrieve with `card`, `confirmer` ("SMS system" / staff username / "admin"), `order_source`, `order_type`; filters on status/method/confirmed_by/bank_card/source
- [x] **Accounting** `/admin/accounting/` — revenue for `period=daily|weekly|monthly` or custom `from`/`to` (accepts **Jalali `YYYY/MM/DD`** or ISO); totals + `by_method` + `by_source` + `by_card` + `daily` series, all ranges rendered Jalali
- [x] **Broadcast** `/admin/notifications/` — create broadcast/targeted `Notification` (via_site/bot/email), list with `delivery_count` + `audience`. (Actual channel fan-out = the notifications-engine phase)
- [x] **Branding** `/admin/branding/` GET/PUT/PATCH `SiteConfig` (name/domain/logo/favicon/bot text, multipart for files) + audit; public `/api/v1/config/` for the frontends
- [x] **Lists** `/admin/services/?filter=expired|on_hold|online` + `/admin/dashboard/` (service counters, online-now)
- [x] **Telegram stats** `/admin/telegram-stats/` — per-channel member counts + total + latest `TelegramStats`
- [x] **RBAC** `/admin/roles/` (with `permission_codes`), `/admin/permissions/` (read), `/admin/staff/` CRUD
- [x] **Pages / themes** `/admin/pages/` + `/admin/themes/` CRUD, `/admin/themes/{id}/activate/`; public `/api/v1/pages/`, `/api/v1/pages/{slug}/`, `/api/v1/theme/`
- [x] No new migrations (adminpanel has no models; `Staff` shims are class attrs). drf-spectacular: 0 errors / 0 warnings (auth extension, enum overrides, renamed `AdminBankCardSerializer`, type hints)
- [x] Verified: **123/123 pytest** (+19: staff login/me/refresh, RBAC per-endpoint + superadmin + break-glass + anon-deny, user filter/CRUD/actions, per-card report, transactions, accounting + Jalali range, broadcast, branding + public, service-list filters, role CRUD, page/theme CRUD + activate + public), no drift, `check --deploy` clean, **live smoke through Nginx** (staff login → me/dashboard/users/accounting[Jalali]/deposit-report, public config/theme, 401 for anon)

## Phase 9 — Monitoring + backup + resources  ✅
- [x] **Health checks** `apps/ops/health.py::run_health_checks()` — probes all 9 targets, each wrapped so a probe never raises, writes a `HealthCheck` row: site (HTTP `HEALTHCHECK_SITE_URL`), mysql (`SELECT 1`), redis (cache round-trip), celery_worker (`app.control.ping`), celery_beat (newest enabled `PeriodicTask.last_run_at` < 30 min), **bot_sales / bot_backup (Redis heartbeat** written by a daemon thread in each `run_*_bot` command, TTL `BOT_HEARTBEAT_TTL`**)**, panel (`PasarGuardClient.check()`), mail (SMTP `connection.open()`)
- [x] **Resources** `apps/ops/resources.py::sample_resources()` — `psutil`: `cpu_percent` / `ram_percent` / `disk_percent` (`RESOURCE_DISK_PATH`), cumulative `net_in`/`net_out`, and `bandwidth_used` = delta since the previous `ResourceStat`
- [x] **Backup** (flowchart 1.8 — built in P7) now with **configurable interval**: `apps/ops/schedule.py::reconcile_backup_schedule()` keeps the `ops: database backup` `PeriodicTask` interval == `backup_interval_minutes`, fired by a `post_save` signal on `Setting` + a beat task + `seed`. `prune_backups_task` deletes files + logs older than `BACKUP_RETENTION_DAYS`
- [x] **Service alerts** `apps/ops/alerts.py::run_service_alerts()` (flowchart 1.9) — for `active`/`on_hold`/`limited` services: volume used ≥ `alert_volume_percent` & not `alert_vol_sent` → alert + set flag; days-left ≤ `alert_expire_days` & not `alert_exp_sent` → alert + set flag. (`renew_service` already clears both flags.) Persian site+bot+email messages
- [x] **Notifications dispatch** `apps/notifications/dispatch.py::notify_user()` — per-channel isolated delivery (site always sent; email via `send_mail` graceful; bot via `sales_client().send_message` graceful), one `NotificationDelivery` row per channel with sent/failed + error. `broadcast()` fans a stored `Notification` to all active users. `deliver_notification_task` wired into P8's broadcast create (`on_commit`) and a **"service ready" notification into `fulfill_order`** (flowchart 1.2)
- [x] **Admin endpoints**: `GET /api/v1/admin/health/` (latest per target + `overall`), `/admin/resources/?limit=` (latest + series), `/admin/backups/` + `POST /admin/backups/run/`; `/admin/dashboard/` extended with health + resources summary
- [x] Beat tasks registered by `seed`: health (2 min), resources (5 min), service alerts (30 min), prune backups (daily). `psutil` added to requirements
- [x] No new migrations. **143/143 pytest** (+20: health per-target incl. down/heartbeat, resource sampling + bandwidth delta, service alerts fire-once/threshold/expiry, backup schedule reconcile + signal, notification dispatch per-channel + isolation, admin health/resources/backups + RBAC + dashboard), no drift, `check --deploy` + schema clean, **live**: real health run = 8/9 up (mail unconfigured, **panel auth ok**, bots "alive", beat "21s ago"), resources cpu/ram/disk sampled, `/admin/backups/run/` → Celery → `BackupLog(ok)`

## Phase 10 — Frontends (React + Vite + Tailwind)  ✅
- [x] **Design system** (shared by both apps): Midnight Aurora palette as **CSS variables driven by `ThemeProvider`** — fetches `/api/v1/theme/`, so a panel theme change restyles with no rebuild; `dark` by default + toggle; glassmorphism (`.glass` / `.card` / `.btn-*`); **Vazirmatn** (Google Fonts); **bilingual fa/en** with automatic `document.dir` RTL/LTR (`I18nProvider`); **Jalali dates** via `Intl('fa-IR-u-ca-persian')` (zero deps); dynamic `<title>` / favicon / logo from `/api/v1/config/`
- [x] **User SPA** `frontend/user/` (route base `/`) — axios client with JWT refresh interceptor, `AuthProvider`. Screens: login · register · verify-email · reset-password (request + confirm) · **dashboard** (service cards: usage bar, days-left Jalali, copyable sub-link, QR link, renew) · **store** (plan grid, custom-volume) · **checkout** (create order → shows exact unique amount + cards + reservation deadline → receipt upload → status poll → redirect on completion) · history · **profile** (change password, referral code + count, theme + language) · help (CMS pages)
- [x] **Admin SPA** `frontend/admin/` (route base `/panel/`, Vite `base:/panel/`) — staff JWT (`/admin/auth/login|refresh|me`), `can(code)` permission gate on the nav. Screens: **dashboard** (services / 30-day revenue / health up-count / CPU-RAM-disk) · **users** (search + is_active filter, enable/disable) · **plans** (full CRUD form) · **payments** (approval queue with receipt image, approve/reject) · **accounting** (period buttons + Jalali `from`/`to`, daily bar chart, by-method / by-source breakdowns) · **cards** (per-card deposit report + grand total) · **monitoring** (9 health targets with colour, resource gauges, backup list + "run backup", 15 s auto-refresh) · **branding** (SiteConfig form + logo/favicon upload) · pages · themes (activate) · roles
- [x] **Compose**: dev = two `node:20-alpine` services running Vite (`:5173` / `:5174`) behind the main Nginx (`nginx/conf.d/caspintunel.conf` rewritten: `/api/` + `/admin/` → Django, `/panel/` → admin Vite, `/` → user Vite, HMR websockets proxied). prod (`docker-compose.prod.yml`) = `frontend/*/Dockerfile` multi-stage (node build → nginx static) wired behind the main Nginx via `nginx/prod.conf`
- [x] No backend changes. Verified: both apps `npm run build` clean in Docker (~250 KB gz-81 KB each); full dev stack (11 containers) boots — `/` and `/panel/` serve the SPAs through Nginx, all `/src/*.jsx` transform, HMR client loads, `/api/v1/*` + `/admin/` + `/api/v1/config/` + `/api/v1/theme/` reachable, SPA registration works end-to-end; prod frontend images build and contain the static bundles. Backend **143/143 pytest** still green

## Phase 11 — Deploy + GitHub + DNS  ✅
- [x] **`install.sh`** rewritten — prompts (incl. optional Cloudflare + GitHub tokens), generates `SECRET_KEY` + Fernet key, `chmod 600 .env`, build → up → migrate → seed → superuser, then optional `configure_dns --apply` + `setup_github.sh`. **`update.sh`** — `git reset --hard @{upstream}` → build → up → migrate + seed (picks up new beat tasks/settings) → collectstatic → clears the update sentinel
- [x] **Update button** — `GET /api/v1/admin/system/` (deployed `VERSION` vs the repo's `main` `VERSION`, `update_available`) + `POST` writes `backups/.update-requested`; `scripts/watch-update.sh` (host cron) runs `update.sh`. Admin SPA Monitoring screen shows version + "به‌روزرسانی" button. `VERSION` bumped to **1.0.0**
- [x] **Domain changeable without rebuild** — `DynamicAllowedHostsMiddleware` adds `site_config.site_domain` (+`www`) to `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` at runtime (60 s cache), env stays the baseline
- [x] **Cloudflare DNS** — `apps/ops/cloudflare.py` + `manage.py configure_dns [--apply]` (idempotent upsert, TXT prefix-matching so unrelated records are never clobbered). **Applied live to `caspin.skin`**: `www` + `mail` A (mail = **DNS-only / grey cloud**), MX → `mail.caspin.skin`, SPF `v=spf1 mx a:mail.caspin.skin ~all`, DMARC `p=quarantine`, generated **2048-bit DKIM** (`default` selector, public key in TXT, private key → `backend/mail-keys/default.private` `0600` git-ignored). Apex A was already correct (left unchanged)
- [x] **GitHub** — `scripts/setup_github.sh` creates the **private** repo and pushes with a command-scoped auth header (token never persisted). `.gitignore` audited: `.env`, `backend/mail-keys/`, `nginx/certs/`, planning `.md`s (root-anchored), `node_modules`, `dist`, `backups/` all excluded — **no secret patterns in any tracked file**
- [x] **No AGPL panel code in the repo** — the panel is only ever reached through `PasarGuardClient` (HTTP); verified nothing from the panel source tree is vendored
- [x] **`docs/`** — README, install, deploy, architecture, api, operations, **security-review** (7 findings triaged: media-auth, phpMyAdmin-in-prod, panel-pw-in-django-admin, staff-refresh-rotation, CSP, secret rotation, test-grant — all documented with disposition)
- [x] Security hardening applied: `DATA/FILE_UPLOAD_MAX_MEMORY_SIZE` 12 MB, `mysqldump` password via `MYSQL_PWD` env not argv, `backups/` bind-mount (host-visible for restore + the update watcher)
- [x] Verified: **153/153 pytest**, no drift, `check --deploy` clean, both SPAs build, DNS records confirmed live (mail = DNS-only)

---

## ✅ Build complete — v1.0.0
All 11 phases done. Backend 153 tests green. See `docs/` and `PROGRESS.md` session log.
Remaining optional work (not in any phase spec): native-Kotlin Android SMS app,
self-hosted mail server (Postfix/Dovecot — DNS is ready, `EMAIL_HOST` wire-up
pending), `telegram_stats` population, a few secondary admin screens.

## Post-1.0 — superuser, menu installer, manual-SSL, offline-prep (2026-09-01, part 3)
- **A) Superuser + privacy**: created the operator superuser + Super Admin Staff (username from `DJANGO_SUPERUSER_*`); removed the old default `admin` account
  and **all smoke-test data** (test users/plans/cards/orders/sms/notifications, monitoring history, audit log).
  Git history rewritten to `caspintunel <deploy@aicaspin.ir>` and the repo **deleted + recreated** on GitHub
  (old-author commits gone). LE account contact → `admin@aicaspin.ir`; mail logs/queue purged. `init-letsencrypt.sh`
  now uses `LETSENCRYPT_EMAIL` (never the site-admin email). Personal name/email appears nowhere except the
  `.env` `DJANGO_SUPERUSER_*` lines (the account itself).
- **B) Menu installer**: `install.sh` rewritten — one command → menu (1 Install / 2 Update / 3 Uninstall / 4 Exit),
  detects install state + deployed VERSION. Install collects domain / site-admin / DB passwords / tz / PMA port /
  TLS mode; generates keys; `chmod 600 .env`; **does NOT ask for panel creds** — prints the "set them in /panel/"
  instruction. Update: "not installed" → stop, else pull/build/up/migrate/seed/collectstatic. Uninstall: confirm by
  domain → `down -v` + optional cleanup.
- **C) Manual SSL**: nginx `entrypoint.sh` picks a cert with precedence manual (`nginx/manual-certs/`) → Let's Encrypt;
  `ssl.conf.template` parametrised (`SSL_CERT`/`SSL_KEY`). `scripts/ssl-manual.sh` validates + installs an uploaded
  pair. Installer TLS choice: auto (LE) / manual (upload). nginx mounts `./nginx/manual-certs`.
- **D) Offline-friendly**: Vazirmatn self-hosted via `@fontsource/vazirmatn` (bundled — **no CDN at runtime**;
  verified in both builds). `docker-compose.offline.yml` (`pull_policy: never`). `scripts/save-images.sh`
  (build + `docker save` all 9 images) / `scripts/load-images.sh` (`docker load`). `install.sh --offline` skips
  build/pull/git/LE/DNS. `image:` tag added to nginx. `docs/offline.md`. **Full Iran offline deploy not done** —
  noted in offline.md (image digest pinning, private registry, host hardening).
- 153/153 tests, no drift, deploy check clean. Stack (13 containers) up, health 9/9, `https://aicaspin.ir` + operator-superuser login verified.

## Post-1.0 — aicaspin.ir DNS applied + HTTPS live + mail server (2026-09-01, part 2)
- **DNS applied on Cloudflare** (`aicaspin.ir` zone, node records untouched): `A @`+`A www` DNS-only → `66.245.202.46`;
  `A mail` DNS-only, `MX → mail.aicaspin.ir`, SPF `v=spf1 mx a:mail.aicaspin.ir ~all`, DMARC `p=quarantine`, DKIM
  (DMS-generated key, published). `configure_dns` gained `--proxied` (default now DNS-only) + `--no-mail`.
- **HTTPS live**: real Let's Encrypt cert for `aicaspin.ir, www.aicaspin.ir, mail.aicaspin.ir` (expires 2026-11-30).
  nginx `entrypoint.sh` (replaces the entrypoint.d approach — worked around the image only running `.d` scripts when
  CMD is `nginx`) enables the 443 vhost when the cert exists + 6-hourly reload. `nginx/conf.d` now uses
  `resolver 127.0.0.11` + variable `proxy_pass` so recreating an upstream container no longer 502s.
  `vite.config.js` `allowedHosts` from `ALLOWED_HOSTS`/`DOMAIN` env (Vite 6 blocks unknown Host headers).
- **Mail server**: `mailserver` service = docker-mailserver 14 (Postfix + Dovecot + OpenDKIM + OpenDMARC),
  `SSL_TYPE=manual` reusing the LE cert, `PERMIT_DOCKER=connected-networks`. `.env`: `EMAIL_HOST=mailserver` port 25,
  `dev.py` uses real SMTP when `EMAIL_HOST` set (console otherwise), `EMAIL_BACKEND` now env-overridable.
  Mailboxes `noreply@` + `test@aicaspin.ir`. **Verified**: app password-reset email → DKIM-signed (`s=default d=aicaspin.ir`,
  `opendkim-testkey` = key OK) → delivered to local INBOX; link uses `https://aicaspin.ir/...`. Health check **mail = green**.
  ⚠️ **Vultr blocks outbound port 25** → external delivery (Gmail) times out; needs `SMTP_RELAY_*` (env vars added, empty)
  or a Vultr port-25 unblock. Firewall: ufw inactive, iptables ACCEPT — 80/443/25/587 all open inbound.
- 153/153 tests, no drift, deploy check clean. Full stack (13 containers) up.

## Post-1.0 — domain switch to aicaspin.ir + direct TLS (2026-09-01, part 1)
- `caspin.skin` has a Cloudflare ToS hold → switched the active domain to **`aicaspin.ir`**
  (its own DNS/zone untouched). `.env` (`DOMAIN`/`ALLOWED_HOSTS`/`CORS`/`CSRF`/`PUBLIC_BASE_URL`/`CLOUDFLARE_ZONE`/`DEFAULT_FROM_EMAIL`),
  `site_config.site_domain` (via `seed`, which now syncs it from `DOMAIN`), settings defaults,
  `.env.example`, `install.sh` prompt, `configure_dns` — all → `aicaspin.ir`. `DynamicAllowedHostsMiddleware`
  verified under prod settings: `aicaspin.ir` allowed, `caspin.skin` rejected. Migration `settings_app/0002`.
- `aicaspin.ir` DNS provider = **Cloudflare** (`edna/otto.ns.cloudflare.com`, same account) — **not applied**
  (awaiting user go-ahead). Needs: `A aicaspin.ir` + `A www` → `66.245.202.46` (proxied). `configure_dns --no-mail` added.
- **Direct TLS**: `certbot` compose service + `scripts/init-letsencrypt.sh` (DNS preflight, webroot issuance,
  nginx restart). nginx: ACME challenge location, `ssl.conf.template` + `40-ssl.sh` entrypoint that enables the
  443 vhost only when a cert exists (missing cert never stops nginx), 6-hourly reload, HTTPS→`127.0.0.1:80` with
  `X-Forwarded-Proto`. `nginx` service now maps `443` + `./nginx/letsencrypt` + `./nginx/certbot-webroot`.
  **Cert not issued yet** — `aicaspin.ir` has no A record; run `init-letsencrypt.sh` after DNS propagates.
- Stack up on HTTP (11 + certbot containers), 153/153 tests, no drift, deploy check clean.

---

## Session log
- 2026-08-31 — Phase 0: read references, created PROGRESS.md, drafted 11-phase plan.
- 2026-08-31 — Phase 1: full DevOps + Django skeleton. Frontend = React+Vite+Tailwind, Android = native Kotlin (locked). 8/8 tests. Dev `.env` (git-ignored) at repo root for local runs — real values come from `install.sh`.
- 2026-08-31 — Phase 2: every model from data-model.md / erd.mermaid across all 9 apps + RBAC + encryption + admin + idempotent `seed` command + real bot compose services. 10 migrations, no drift, **18/18 tests**, full 9-container stack boots. Note: user's phase numbering (P1=skeleton, P2=all models) differs from the old draft plan — PROGRESS renumbered; phases 3–11 are now a tentative roadmap.
- 2026-09-01 — Phase 3: full auth surface under `/api/v1/auth/` (register/login/logout/refresh/me/change-password), outage-aware email verification (flowchart 1.1), 3-path password reset (flowchart 1.6), legacy import (endpoint + mgmt command), `auth` throttle scope. Added `token_blacklist` + `config.settings.test`. **35/35 tests**, no drift, live smoke test green.
- 2026-09-01 — Phase 4: panel integration. **Discovered the panel is PasarGuard API v5.3.0, not Marzneshin** — rewrote the client to match `/openapi.json`. `PasarGuardClient` (token cache + re-auth + typed errors), payload mappers (On-Hold for timed plans via `status:on_hold`), idempotent `provision/renew/sync` services, retry-safe Celery tasks + `sync_all_services` beat task, `panel_check` command. Renamed `default_service_ids`→`default_group_ids`. Verified against the **real panel** (auth, 21 nodes, 4 groups). **51/51 tests**.
- 2026-09-01 — Pre-P5 + Phase 5: `Plan.group_ids` (admin CheckboxSelectMultiple, default `[5,6,8,10]`) with panel-default fallback; plans API + admin CRUD; orders API with atomic unique-amount reservation (flowchart 1.2); card-to-card receipt → admin approve/reject (1.3); retry-safe `fulfill_order` (provision/renew/addon, 1.5); services API + QR PNG; 3 new migrations; reservation-expiry beat task. **74/74 tests**, live smoke green (approve→provision NOT run against prod panel).
- 2026-09-01 — Phase 6: SMS auto-confirm (flowchart 1.4). `SmsDeviceAuthentication` (X-Device-Token), Persian/rial-aware amount parsing, matching engine → `Payment(sms_auto, confirmed_by=system)` + fulfillment, `POST /payments/sms/inbound/` + `/sms/ping/`, sender allow-list via `sms_source`. No new migrations. **83/83 tests**, live smoke green.
- 2026-09-01 — Phase 7: Telegram bots. `TelegramClient` (raw API, proxy, independent), `ensure_bot_user` (first-time → random site creds), forced-channel + phone gate (1.7), sales bot (pyTelegramBotAPI: buy/renew/custom/status/QR), separate backup bot + `run_database_backup` (mysqldump→gz→send, never crashes), beat tasks for backup + channel counts. Compose: shared `caspintunel-backend` image, `backups_data` volume, `default-mysql-client`. **104/104 tests**.
- 2026-09-01 — Phase 8: admin panel API. New `apps/adminpanel/` — Staff JWT + own-RBAC `StaffPermission` (superadmin bypass, Django-superuser break-glass), `seed` bootstraps a Super Admin Staff from `DJANGO_SUPERUSER_*`. Endpoints under `/api/v1/admin/`: users, plans, cards + **per-card deposit report**, transactions (card/confirmer/source), **Jalali accounting**, broadcast notifications, branding (`SiteConfig`) + public `/config/`, service lists + dashboard, telegram-stats, roles/permissions/staff, pages/themes + public `/pages/` & `/theme/`. **123/123 tests**.
- 2026-09-01 — Phase 9: monitoring. `apps/ops/` health checks (9 targets, bots via Redis heartbeat thread), `psutil` resource sampling (+bandwidth delta), configurable backup interval (`Setting` signal → `reconcile_backup_schedule`), service alerts (flowchart 1.9), `apps/notifications/dispatch.py` per-channel isolated delivery + wired into broadcast & `fulfill_order`. Admin `/admin/health|resources|backups/` + dashboard. **143/143 tests**.
- 2026-09-01 — Phase 10: frontends. `frontend/user/` + `frontend/admin/` — React 18 + Vite 6 + Tailwind 3, shared design system (Midnight Aurora CSS-var palette from `/api/v1/theme/`, dark default, glass, Vazirmatn, fa/en RTL/LTR, Jalali via Intl, dynamic branding from `/api/v1/config/`). User: full auth + dashboard + store + checkout + profile + help. Admin: staff-JWT + dashboard/users/plans/payments/accounting/cards/monitoring/branding/pages/themes/roles. Compose: dev Vite services + rewritten Nginx routing; prod multi-stage static images + `nginx/prod.conf`. Backend untouched (143/143).
- 2026-09-01 — Phase 11 (final): `install.sh`/`update.sh` rewritten, panel Update button (`/admin/system/` + sentinel + `watch-update.sh`), `VERSION` 1.0.0, `DynamicAllowedHostsMiddleware` (domain change, no rebuild). `configure_dns` command — **applied live to caspin.skin** (www/mail A, MX, SPF/DKIM/DMARC; mail DNS-only; 2048-bit DKIM key generated). `setup_github.sh` (private repo, ephemeral auth). `docs/` (6 files incl. security-review). Hardening: upload cap, `MYSQL_PWD` env, backups bind-mount. **153/153 tests**, no drift, deploy check clean. **Build complete.**
- 2026-09-01 — Monitoring page rebuilt to the glass-card mockup. New aggregate endpoint `GET /api/v1/admin/monitoring/` (`MonitoringView`) — one 15 s snapshot: 9 health targets (badge + latency), CPU/RAM/disk from `psutil` + 24 h avg/peak from `ResourceStat`, live bandwidth (up/down bps + lifetime totals), rolling 40-point network series, recent 6 backups, server IPs + open-socket counts. `apps/adminpanel/hostnet.py` reads the host net namespace via `/hostproc/1/net` (host `/proc` bind-mounted `:ro`; degrades to container `/proc/net`) — real NIC byte counters, `sockstat` TCP/UDP inuse, `fib_trie` local IPs. Frontend `Monitoring.jsx` fully rewritten to match the mockup (r4/r2 grid, top gradient lines, SVG traffic graph), `format.js` gains `faDigits`/`relTime`/`bps`. `SERVER_IP` setting added for offline hosts. Backend untouched at 153/153.
- 2026-09-01 — Admin config screens + mobile nav. New `apps/adminpanel/views/integrations.py`: `GET/PUT /api/v1/admin/integrations/panel/` (Pasargad base URL, admin username/password, subscription base URL, group ids, verify-SSL — `settings.manage`), `POST .../panel/test/` (live `client.check()` probe), `GET/PUT .../integrations/telegram/` (both bots keyed by type: token, proxy; backup also chat_id — `bots.manage`). Secrets are write-only (`admin_password` / `token`) — reads return only `*_set` booleans; blank on save keeps the stored secret; saving drops the cached panel token. New admin pages `Integrations.jsx` → routes `/panel-link` ("اتصال پنل پاسارگارد") and `/bots` ("ربات‌های تلگرام") added to the sidebar. `Plans.jsx` reworked: Fixed vs Volume-based picker cards with plain-language descriptions, volume inputs in **GB** (converted to bytes), "empty = unlimited" hints on volume/duration/device limit, bilingual customer **Description** (`desc_fa`/`desc_en`) — shown on the user Store per language. Both SPAs: sidebar → off-canvas hamburger drawer under `md` (backdrop, `start-0`, RTL/LTR slide). **+9 tests (test_integrations.py)**, deploy check clean.
