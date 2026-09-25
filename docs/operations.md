# Operations

## Backups (flowchart 1.8)
- `mysqldump` → gzip → `backups/<project>-<ts>.sql.gz`, logged in `backup_log`, sent
  via the backup bot to `backup_chat_id` if configured. A Telegram outage is logged
  on the entry, never fatal.
- Interval = `backup_interval_minutes` setting; changing it live re-schedules the
  beat task (signal on `Setting` save).
- Retention: `prune_backups_task` deletes files + logs older than `BACKUP_RETENTION_DAYS`.
- Manual: panel → Monitoring → "Run backup", or
  `docker compose exec celery_worker python -c "from apps.telegram.backup import run_database_backup; run_database_backup()"`
- Restore: `gunzip < backups/x.sql.gz | docker compose exec -T db mysql -u root -p<root> caspintunel`

## Monitoring
- Panel → Monitoring: 9 health targets, CPU/RAM/disk gauges, backup list, version/update.
- Health probes run every 2 min (`health_check` rows); resources every 5 min.
- Bots report a Redis heartbeat from a daemon thread — "alive" even while idling
  without a token.

## Service alerts (flowchart 1.9)
Every 30 min: for `active`/`on_hold`/`limited` services, if usage ≥
`alert_volume_percent` or days-left ≤ `alert_expire_days` and the matching
`alert_*_sent` flag is unset → notify (site + bot + email) and set the flag.
Renewing a service clears both flags.

## Panel connectivity
`docker compose exec web python manage.py panel_check` — auth, system stats,
node status, and the group ids to put in `Plan.group_ids` / `Panel.default_group_ids`.

## Common tasks
| Task | How |
|---|---|
| add a plan | panel → Plans (pick panel groups via checkboxes) |
| add a bank card | panel → Cards (mobile: Settings → Bank cards) |
| register an SMS device | panel → Settings → SMS devices → "Add device" → copy the token into the Android app / iPhone shortcut |
| get the Android app / iPhone shortcut | panel → **Apps & tools** — downloaded from this server (the bundled APK comes from `mobile_sms/release/`; admins can upload a newer APK or the `.shortcut` file) |
| add a forced channel | panel → Telegram bots → required channels; make the sales bot an admin of the channel |
| delete a user | panel → Users → "Delete user" (reason required, perm `users.delete`): services are **disabled** on the panel, a full snapshot is archived, username/phone/email are freed, sessions revoked, Telegram unlinked; orders/payments stay (accounting unchanged) |
| restore a deleted user | panel → Users → Deleted users → entry → Restore (blocked if the original username/phone/email is taken again; services stay disabled until re-enabled) |
| attach an existing panel account to a user | panel → Services → Create manual service → "Link existing panel service" (live panel search; nothing changes on the panel) |
| rotate a leaked secret | edit `.env`, `docker compose up -d` the affected service (no rebuild); rotate `FIELD_ENCRYPTION_KEY` requires re-encrypting rows |
| change alert thresholds / toggles | panel settings (`setting` table) |

## Logs
`docker compose logs -f web celery_worker bot_sales` — app logs go to stdout
(`caspintunel` logger). `audit_log` records staff actions.
