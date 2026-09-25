# Architecture

API-first Django. One backend, versioned API (`/api/v1/`, JWT), multiple
independent frontends. Jalali calendar in the presentation layer (UTC stored).
Bilingual fa/en.

## Backend apps (`backend/apps/`)

| App | Responsibility |
|-----|----------------|
| `common` | base model, encrypted fields (`FIELD_ENCRYPTION_KEY` / Fernet), Jalali helpers, audit log, `DynamicAllowedHostsMiddleware`, health/root views |
| `accounts` | customer `User` (`AUTH_USER_MODEL`), independent RBAC — `Permission` / `Role` / `Staff`; JWT auth (password-hash claim revokes sessions), registration (terms accepted at sign-up), phone normalization / Iran-only rule, outage-aware email verification, 3-path password reset, legacy import, bot↔site account merge, **soft delete + `DeletedUserArchive`** snapshot / restore (`accounts/deletion.py`) |
| `panel` | multi-panel `Panel` + `PasarGuardClient` (token cache, typed errors), `Service`, payload mappers, idempotent provision/renew/sync, scheduled renewals (reset / carry-over), admin full edit (status, volume, expiry, groups, note, HWID limit), manual create + **link an existing panel account**, retry-safe Celery tasks, `Service` read API + QR |
| `plans` | `Plan` (fixed / custom-volume), `group_ids` per plan with panel-default fallback |
| `orders` | `Order` (new / renew / add-on / manual / imported), atomic unique-amount reservation (`amount_unique_lock`), checkout resume, `fulfill_order` + `retry_unfulfilled_orders` tasks |
| `payments_sms` | `BankCard`, `Payment`, card-to-card flow; `SmsSource` / `SmsAppDevice` / `SmsMessage`, `SmsDeviceAuthentication`, rial-aware parser, auto-match engine |
| `notifications` | `Notification` / `NotificationDelivery`, `dispatch.notify_user` (per-channel isolated: site / email / bot), Channels WebSockets: customer notifications + staff live payments queue |
| `telegram` | `TelegramClient` (raw API, proxy), `ensure_bot_user`, forced-channel + phone gate (asked again on any message), sales bot (pyTelegramBotAPI; every service is sent as a QR photo with the subscription link as tap-to-copy `<code>`), Mini App login, backup bot, `run_database_backup` |
| `settings_app` | `Setting` (typed KV), `SiteConfig` (branding singleton), `Theme`, `Page`, **`AppRelease`** (operator apps served from this server); public config/theme/pages endpoints; interval-reconcile signal |
| `ops` | `HealthCheck` / `ResourceStat` / `BackupLog`, health probes, `psutil` sampling, service alerts, Cloudflare `configure_dns` |
| `adminpanel` | the operator API under `/api/v1/admin/` — Staff JWT + `StaffPermission`, all management endpoints |

## Async

Celery + Redis. Beat schedule (created by `seed`, DB scheduler):
panel sync (`service_sync_interval_minutes`) · reservation expiry (5 m) · due scheduled renewals (5 m) ·
retry unfulfilled paid orders (10 m) · DB backup (`backup_interval_minutes`) ·
channel member counts (60 m) · health (2 m) · resources (5 m) · service alerts (30 m) ·
prune old backups (24 h).

## Frontends (`frontend/user`, `frontend/admin`)

React + Vite + Tailwind SPAs, themes driven by `/api/v1/theme/` (Midnight Aurora,
Royal Frost, Caspian). **Offline-safe:** every font and asset is bundled at build
time (`@fontsource`) — nothing is loaded from a CDN, so the site works on a server
with only Iranian/national internet. Fonts: Persian UI = **Vazirmatn** everywhere,
English UI = **Inter** (Vazirmatn fallback), JetBrains Mono only for `<code>`.
One shared `ConfirmDialog` (bottom sheet on phones) for every confirmation.
Admin on phones (Caspian): bottom nav = dashboard · users · payment queue (centre,
live badge) · services · settings; Settings is the index of every other page, each
settings section has its own route (`/panel/settings/<section>`).

## Money flow

`create_order` → unique surcharge 200–1500 tomans reserved (30 m) → pay the exact
amount → **SMS auto-match** (`Payment.confirmed_by=system`) **or** receipt upload
+ admin approve → `order.paid` → `fulfill_order` (create/renew on panel, retry on
`PanelUnavailable`) → `order.completed` + "service ready" notification.

Timed plans use panel **On-Hold** (`status="on_hold"` + `on_hold_expire_duration`)
so the clock starts on the user's first connection. Renewal keeps the same panel
username and subscription URL.

## Security posture

See `LICENSE` (proprietary) and `docs/operations.md`. Secrets live only in `.env`
(git-ignored); panel password, bot tokens and the panel API token are encrypted
at rest. Three token audiences: customer JWT, staff JWT, per-device SMS token.
