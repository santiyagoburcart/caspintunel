# Development, tests and releases

## Tests — isolated stack only
```bash
./scripts/test.sh                       # whole suite
./scripts/test.sh apps/telegram -k history   # any pytest args
```
`docker-compose.test.yml` (project `caspintunel-test`): its own network, a
throw-away MySQL + Redis on tmpfs, per-run keys, nothing from `.env`.
`config/settings/test.py` refuses to start unless the DB host is `test-db` and
Redis is `test-redis`. **Never** point tests or scripts at the live DB/Redis.

Notes: tests touching `transaction.on_commit` need
`@pytest.mark.django_db(transaction=True)` and a stubbed `fulfill_order.delay`;
bot handler tests stub `close_old_connections`. Decode tests use `zxing-cpp`
(skipped if the image predates it).

## UI rules (both SPAs)
- every string fa + en; **digits always Latin** (fa Intl formatters need `-u-nu-latn`);
  Jalali via `lib/format.js`;
- colours from `var(--c-*)`; badge/pill **text** uses the contrast-safe `--c-*-fg`
  tokens (`success`, `danger`, `warning`, `primary`, `secondary`, `muted`);
  *expired* is always neutral gray (`muted`);
- one popup (`components/ConfirmDialog.jsx` + `useConfirm()`), one copy helper
  (`lib/clipboard.js`); never `window.confirm/alert/prompt`;
- phones (≤ 767 px): inputs 16 px (no iOS zoom), tap targets ≥ 44 px, compact
  record-grid cards instead of wide tables, page subtitles hidden, KPI tiles 2 per row;
- a new admin page goes in the sidebar (`components/Layout.jsx`), the mobile
  Settings index (`pages/Settings.jsx` `HUB_GROUPS`) and `MOBILE_TITLES`.

## Releasing
1. bump `VERSION`, commit, tag `vX.Y.Z`, push `main` + the tag;
2. on the server: `./update.sh` (backup → build → migrate/seed/collectstatic once →
   rolling swap of web, daphne and both SPAs → `up -d` for the rest, bots included);
3. rollback: `./update.sh --rollback` (images; restore the pre-update dump only if a
   migration must be undone).

Migrations run while the previous release still serves: add columns now, drop
them a release later. Build images only through `update.sh`.

## Archived work
The rejected "Liquid Glass" UI refresh is kept, unmerged, on branch `ui-refresh`
and tag `archive/ui-refresh-liquid-glass` (see `PROGRESS.md`).
