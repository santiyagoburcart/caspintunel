# Agency panel ← PAMP v1.5.3 — porting map

Source: https://github.com/santiyagoburcart/PAMP tag `v1.5.3` (commit `1d69332`), read-only.
The Finland server runs the same calculation files (sha256 identical, checked 2026-10-16).

| PAMP file (sha256) | agency file | what changed |
|---|---|---|
| `admins/models.py` (`9a6a8316…53a9`) | `models.py` | **verbatim**: every field, default, property and `_fmt_bytes` (1024-based). Added only `db_table = "agency_*"`. Not ported: `PanelConfig` (→ caspintunel `panel.Panel`), `SyncSettings` (→ setting `agency_sync_interval_minutes`), `UISettings`, `TelegramConfig`. |
| `admins/panel_api.py` (`7d9d2aa0…6946`) | `panel_api.py` | **verbatim** incl. the v1.5.3 error handling (`DEFAULT_USERS_LIMIT` 4096 cap, raise on bad `/api/users`, per-admin skip). Only `__init__` reads `agency_panel()` (setting `agency_panel_id`, else the first active panel) instead of `PanelConfig`; `verify=False` kept as in PAMP. |
| `admins/tasks.py` (`c0145a1e…91e4`) | `tasks.py` | `track_deleted_users`, the sync body (`_pamp_sync`) and `check_and_enforce_limits` **verbatim**, same order of operations. Added: the task returns `"disabled"` unless setting `agency_sync_enabled`; enforcement runs only with `agency_enforcement_enabled` (both default **off**). Removed: `User.objects.get_or_create(username=…)` (resellers must not become caspintunel users) and the Telegram backup task. Task name `apps.agency.tasks.sync_panel_admins`, same `max_retries=3`, `default_retry_delay=60`. |
| `admins/views.py` (`cf8e262f…65cf`) | `enrich.py` | `_fmt_bytes_signed` and `_enrich` **verbatim** (note: hidden traffic is *not* clamped there, unlike the model property); `dashboard_numbers()` = body of `dashboard_v2`; `portal_state()` = body of `portal_v2` (v1.5.3 `limit_config.support_telegram` fix). No HTML views yet (phase 1). |
| `admins/backends.py` | — | reseller portal login comes in a later phase. |
| MySQL dump | `pamp_import.py`, `manage.py import_pamp_dump` | 1:1 copy of admins, limits, snapshots, sync logs, groups with their original ids and timestamps; re-read and compared field by field before commit. |

## Proof

`tests/test_golden.py` + `golden/` + `scripts/agency-golden.sh`:

* `golden/expected_pamp_v153.json` is produced by the **original** PAMP v1.5.3 code (its own image: Python 3.11,
  Django 4.2, MySQL 8, PAMP's own settings; `render` captured so dashboard/portal numbers come from PAMP's views)
  on `golden/scenario.json` — 6 sync rounds covering deleted users, `/api/users` 500 and timeout (skip), the
  4096 cap, empty and failed `/api/admins` (retries), block / unblock / failed PUT, added and removed admins,
  unlimited admins, groups, negative hidden traffic, rounding.
* The agency app runs the same rounds with the same mocked responses; every stored field, formula, view
  number, snapshot, SyncLog row and HTTP call (= enforcement decision) must be identical. A one-character
  change in a formula fails it.
* With `backend/.golden_local/real/` present (local only, git- and docker-ignored) the same comparison runs on
  the real Finland dump and real recorded sigma responses.

## Rules

* Do not edit formulas or the sync order here — change PAMP first, re-port, regenerate the golden file.
* Never enable `agency_sync_enabled` while the Finland PAMP still syncs (two syncs = double accumulation and
  enforcement on one panel).
