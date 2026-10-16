# Agency panel (پنل نمایندگی)

Reseller-admin management ported from PAMP v1.5.3 into caspintunel (app `backend/apps/agency`): the
PasarGuard admins (resellers), their limits, used / sold / hidden traffic, deleted-users accounting,
enforcement (disable an admin at 100 % of their limit, re-enable below it) and account groups.
Phase 1 = backend + data import; phase 2 = admin UI. Porting map: `backend/apps/agency/PORTING.md`.

## Admin UI (`/panel/agency`, permission `agency.view`)

Dashboard (PAMP totals: Total Sold, Used, Remaining, Hidden, admins; the ≥80 % list) · Admins (search,
status / limit / group filters, usage bar, Total Sold, Sold Limit, Hidden, Remaining) · admin detail (every
PAMP number, user counts, snapshots, recent syncs, actions) · Groups · Sync logs · Settings (sync,
enforcement, interval; `agency.manage`). Every number comes from the backend (`apps/agency/api.py` only
selects values computed by the ported code); the pages only format them.

**Until the cut-over every write is off**: set/remove limit, enable/disable admin or all their users, reset
deleted traffic, sync now and group edits answer `409 pre_cutover` and the buttons show "فعال پس از انتقال
نهایی". They open when `agency_sync_enabled` is turned on — which the Settings page only accepts after typing
`FINLAND-STOPPED` (that switch IS the cut-over). Enforcement can only be on while sync is on.

API: `GET /api/v1/admin/agency/` · `agency/admins/` · `agency/admins/<username>/` ·
`POST agency/admins/<username>/{set-limit|remove-limit|admin-action|reset-deleted-traffic}/` ·
`POST agency/sync-now/` · `agency/groups/` · `agency/sync-logs/` · `GET/PATCH agency/settings/`.

## Switches (all OFF by default)

| setting | default | meaning |
|---|---|---|
| `agency_sync_enabled` | `false` | the periodic task `agency: sync panel admins (PAMP)` does nothing while off |
| `agency_enforcement_enabled` | `false` | even with sync on, nobody is disabled/enabled on the panel |
| `agency_sync_interval_minutes` | `15` | beat interval (taken from PAMP's setting by the import) |
| `agency_panel_id` | *(unset)* | panel to sync; unset = first active panel (sigma.hunaex.shop) |

**Never turn sync on while the Finland PAMP still syncs** — two syncs against one panel would each count
deleted users and each enforce.

Permissions: `agency.view`, `agency.manage` (Super Admin role only by default).

## Importing PAMP data

```bash
# on the PAMP server: consistent dump (PAMP keeps running)
docker compose exec -T db sh -c 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction \
  --no-tablespaces --default-character-set=utf8mb4 "$MYSQL_DATABASE"' | gzip > pamp.sql.gz
# here (file under backups/, which web mounts)
docker compose exec web python manage.py import_pamp_dump /app/backups/pamp/pamp.sql.gz --dry-run
docker compose exec web python manage.py import_pamp_dump /app/backups/pamp/pamp.sql.gz --replace
```

Copies admins, limits, user snapshots, sync logs and account groups 1:1 (same ids, timestamps, byte counters,
`deleted_users_used_bytes`), re-reads every value and compares it with the dump before committing. Not
imported: PAMP's Django users and sessions (resellers never become caspintunel users), its panel password,
Telegram and UI settings. Refuses while `agency_sync_enabled` is on.

## Cut-over (later, on your approval)

1. Finland: stop `celery` + `celery-beat` (no more syncs).
2. Fresh dump → `import_pamp_dump … --replace`.
3. Turn on `agency_sync_enabled`, watch the first syncs, then `agency_enforcement_enabled`.

## Golden test

`./scripts/agency-golden.sh synthetic` regenerates the expectations by running the ORIGINAL PAMP v1.5.3
(its own image and a throw-away MySQL); `./scripts/test.sh apps/agency` compares the agency app with them.
`./scripts/agency-golden.sh real DUMP RESPONSES` does the same with real data (kept in
`backend/.golden_local/`, never committed).
