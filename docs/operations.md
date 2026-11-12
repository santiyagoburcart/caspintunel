# Operations

## Backups (flowchart 1.8)
- `mysqldump` → gzip → `backups/<project>-<ts>.sql.gz`, logged in `backup_log`, sent
  via the backup bot to `backup_chat_id` if configured. A Telegram outage is logged
  on the entry, never fatal.
- Interval = `backup_interval_minutes` setting; changing it live re-schedules the
  beat task (signal on `Setting` save, `apps/ops/schedule.py`).
- Retention (`apps/ops/retention.py`, hourly `prune_backups_task`, or
  `docker compose exec celery_worker python manage.py cleanup_backups [--dry-run]`):
  - DB backups: deleted after **Settings → Backup → Keep local copies (days)** (default 2) — only
    once Telegram confirmed the upload (`sent_to_telegram`). Unsent ones are re-sent hourly; if that
    fails they stay and the backup chat gets an alert (at most every 6 h). The newest 2 always stay.
  - Dumps above Telegram's 50 MB bot limit are sent as `<name>.partNN` pieces
    (`cat <name>.part* > <name>` to join); a failed piece = not sent.
  - `backups/pre-update-*.sql.gz` (update.sh): newest 3 stay. `backups/migration/*`: deleted after 7 days.
  - Docker: `scripts/docker-cleanup.sh` (end of every `update.sh`) removes untagged images and build
    cache unused for 72 h; `:latest` + `:rollback` (= the previous release) stay.
  - Monitoring → "Disk & cleanup" shows disk usage, what `backups/` holds, the last run and kept files.
- Manual: panel → Monitoring → "Run backup", or
  `docker compose exec celery_worker python -c "from apps.telegram.backup import run_database_backup; run_database_backup()"`
- Restore (**live data — ask first, take a fresh dump before**): `gunzip -c backups/x.sql.gz | docker compose exec -T db sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"'`

## Monitoring
- Panel → Monitoring: 8 health targets (site, MySQL, Redis, Celery worker, Celery beat, sales bot, backup bot, mail),
  CPU/RAM/disk gauges, disk & cleanup, backup list, version/update.
- Health probes run every 2 min (`health_check` rows); resources every 5 min. Disk alerts (v1.25.2, `apps/ops/disk.py`)
  are checked before any DB write; the host cron writes `backups/.disk-report.json` daily, read by `ops: daily disk report`.
- Bots report a Redis heartbeat from a daemon thread — "alive" even while idling without a token.
- **Container memory** (v1.39.0): Monitoring → «حافظهٔ کانتینرها» — each container of this project against its memory limit,
  OOM kills, restarts, host swap, memory pressure and load (from the host cron `scripts/container-stats.sh`, every 5 min).
  Telegram alerts: ≥ 85 % of a limit, OOM kill / restart, swap ≥ 1.5 GB for 30 min, pressure ≥ 10 %, load above the CPU count,
  report stale. A killed container restarts by itself (`restart: unless-stopped`); raise its limit in `docker-compose.prod.yml`
  only when it is killed again after a normal day. Run builds and the test stack one at a time on this server.
- Payments → «واریزهای بلو»: Blu collector service state over SSH (read-only), last successful poll, last error
  ([blu-webhook.md](blu-webhook.md)).
- **Unconfirmed-payment alert** (v1.33): a payment pending longer than `pending_payment_alert_minutes` (Settings → Alerts,
  default 5, 0 = off) → one Telegram to `payment.approve` staff + live event + browser push; a silent "resolved" follow-up.

## Pre-expiry warnings (retention, v1.20) / service alerts
Every 30 min `ops: service alerts` runs the **retention warnings** (`apps/crm/retention.py`): configurable `WarningRule`s
(volume % / days left), unique per service, kind, threshold and period, quiet hours (`retention_quiet_start/end`),
channels tracked per warning; CRM → Retention. Only when `retention_warnings_enabled` is off does the old fixed alert run
(usage ≥ `alert_volume_percent` or days-left ≤ `alert_expire_days`, `alert_*_sent` flags cleared on renewal).

## Panel connectivity
`docker compose exec web python manage.py panel_check` — auth, system stats,
node status, and the group ids to put in `Plan.group_ids` / `Panel.default_group_ids`.

## Common tasks
| Task | How |
|---|---|
| add a plan | panel → Plans (pick panel groups via checkboxes) |
| add a bank card | panel → Cards (mobile: Settings → Bank cards) |
| register an SMS device | panel → Settings → SMS devices → "Add device" → copy the token into the Android app (the iPhone Shortcut download can fill it in for you) |
| get the Android app / iPhone shortcut | panel → **Apps & tools** — downloaded from this server (the bundled APK comes from `mobile_sms/release/`, admins can upload a newer APK; the iPhone Shortcut is built from `mobile_shortcut/CaspinSMS.shortcut` on each download — pick an SMS device to fill in its token; sign it on a Mac with `shortcuts sign --mode anyone` or use an iCloud link) |
| add a forced channel | panel → Telegram bots → required channels; make the sales bot an admin of the channel |
| delete a user | panel → Users → "Delete user" (reason required, perm `users.delete`): services are **disabled** on the panel, a full snapshot is archived, username/phone/email are freed, sessions revoked, Telegram unlinked; orders/payments stay (accounting unchanged) |
| permanently delete a deleted user | Users → Deleted users → «حذف دائمی» (Super Admin + `users.purge`; preview first, optional delete on PasarGuard). The row is anonymized, orders / payments stay. Auto-purge after N days: Deleted users → settings (off by default) |
| delete (void) / restore a transaction | Transactions → row → «حذف» (Super Admin, reason, choose what happens to the service); restorable for 30 days; voided rows leave every total |
| record a payment made outside the site | Users → user → «+ فاکتور دستی» (or CRM 360), mode «قبلاً پرداخت شده»; or issue an invoice the customer pays in their panel (`payments.manual_invoice`) |
| discount codes | CRM → Discount codes (`DiscountCode`; per-code report, usage on paid orders) |
| a Blu deposit did not match | Payments → «واریزهای بلو» → attach it to an order (`payment.approve`) |
| agency: approve volume requests | Agency → Approvals (single, bulk) or the Telegram buttons; prices per GB must exist first |
| agency: invoices out of step with the ledger | `docker compose exec web python manage.py reconcile_agency_invoices` (preview) → `--apply` |
| agency: check admins' profile title / support link | `docker compose exec web python manage.py check_admin_profiles` (preview) → `--apply` |
| sign out a staff member everywhere | `docker compose exec web python manage.py revoke_staff_sessions --username X` (or change their password) |
| browser notifications (Web Push) | set `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` in `.env` → `docker compose up -d` backend services; each person turns it on in Settings |
| tickets | Tickets (inbox, topics, canned replies, staff topic scopes); staff link Telegram with `/start staff-<code>` in the sales bot |
| restore a deleted user | panel → Users → Deleted users → entry → Restore (blocked if the original username/phone/email is taken again; services stay disabled until re-enabled) |
| attach an existing panel account to a user | panel → Services → Create manual service → "Link existing panel service" (live panel search; nothing changes on the panel) |
| rotate a leaked secret | edit `.env`, `docker compose up -d` the affected service (no rebuild); rotate `FIELD_ENCRYPTION_KEY` requires re-encrypting rows |
| change alert thresholds / toggles | panel settings (`setting` table) |
| bot support contact / message | panel → Branding → *Telegram bot support* (IDs comma-separated; fa/en text, e.g. working hours) |
| QR background for customers | panel → Branding → *Subscription QR background* (built-in or custom upload; applies to bot, site and downloads at once) |
| an SMS shows "amount mismatch" | the SMS equals an open invoice only after a Rial/Toman change (e.g. 10× too little) — never auto-approved; compare with the bank statement and approve/reject by hand. Each bank number has an *SMS amount unit* (Settings → Bank numbers), used when the SMS names no unit |
| why didn't an SMS confirm a payment? | panel → SMS log (masked text, parsed amount, matched order or the reason) |
| a rejected order was paid after all | approve it from Transactions — late approvals are fulfilled normally |
| read the docs on the server | panel → Documentation (`docs/*.md`, read-only) |
| run the tests | `./scripts/test.sh` — isolated stack only, never the live DB |
| change the domain / access mode | Settings → Domain & Cloudflare (wizard, rollback) — [domain.md](domain.md), [access-mode.md](access-mode.md); recovery `./scripts/domain.sh show | rollback` |
| change / recover the admin or portal path | Settings → Paths, or `./scripts/paths.sh show / reset / set-admin /x / set-portal /y` ([paths.md](paths.md)) |
| move to a new server | `scripts/migrate-export.sh` → `scripts/migrate-import.sh` — runbook in [migration.md](migration.md) |
| maintenance mode (503 page, nothing reaches the app) | `touch nginx/flags/maintenance` / `rm nginx/flags/maintenance` |
| keep bots + celery idle | `MIGRATION_HOLD=1` in `.env` + `docker compose up -d --force-recreate bot_sales bot_backup celery_beat celery_worker` |
| open a store for a reseller | Agency → admin → «فروشگاه» → «ساخت فروشگاه» (draft) → domain (direct / Iran tunnel; give the reseller the exact records shown) → bot token → owner login → status «فعال» — step by step: [pilot-fa.md](pilot-fa.md) |
| a store domain is stuck | «فروشگاه» → domain → «بررسی الان» / «تلاش دوباره»; host log `/var/log/caspintunel-tenants.log` (watcher `scripts/tenants.sh`, every minute); test the watcher only with `scripts/test-tenants.sh` |
| suspend / close a store | «فروشگاه» → status: its domains show the «در دسترس نیست» page (503) within about a minute; nothing is deleted |
| a store's failed orders («ساخت ناموفق») | «فروشگاه» → «سفارش‌های ناموفق» → retry (same paid order) — or the store's own Payments page |
| store backup / monthly fee | «فروشگاه» → backups (one-time link, 24 h) · fee settings (off by default; `agency.accounting`) |
| import a reseller's old bot | «فروشگاه» → «ورود داده از ربات قبلی»: upload the dump → check the preview + CSV → stop the old bot → tick the checklist → «شروع ورود»; «بازگردانی» undoes it ([store-import.md](store-import.md)) |
| WireGuard locations / file names | Plans → «مکان‌های وایرگارد» (names, flags, file name = tunnel name ≤ 15 chars, optional template); plan type ساب / فقط وایرگارد / هر دو ([wireguard.md](wireguard.md)) |
| an agency admin was removed | it is archived, not deleted: Agency → Admins → «بایگانی»; it comes back by itself when the username is on PasarGuard again ([agency.md](agency.md#archive-instead-of-delete-v154)) |
| agency history | Agency → حسابداری → «تاریخچه» (7 days / month / custom / 12 months, CSV / Excel) |
| roll back a bad release | `./update.sh --rollback` (images); restore `backups/pre-update-*.sql.gz` only if a migration must be undone |

## Logs
`docker compose logs -f web celery_worker bot_sales` — app logs go to stdout
(`caspintunel` logger). `audit_log` records staff actions. Host jobs log to `/var/log/caspintunel-{update,paths,domain,disk,containers,tenants}.log`.

## Management commands
`seed` · `panel_check` · `cleanup_backups [--dry-run]` · `revoke_staff_sessions [--username]` · `reconcile_agency_invoices [--apply]` ·
`check_admin_profiles [--apply]` · `import_pamp_dump` · `import_legacy` · `configure_dns [--apply] [--proxied] [--no-mail]` ·
`cloudflare_token` · `send_test_email` · `set_bot_menu` · `link_blu_deposits [--dry-run]` (v1.42.2 one-time backfill: link unmatched Blu deposits to already approved payments — link only) · `watch_payments` (v1.48: follow the next real payments of our store, alert when one is not matched automatically — read-only except alerts) · `run_sales_bot` / `run_backup_bot` (the bot containers).
Run them with `docker compose exec web python manage.py …` — every command here touches the **live** database.
