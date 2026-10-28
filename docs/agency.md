# Agency panel (پنل نمایندگی)

Reseller-admin management ported from PAMP v1.5.3 into caspintunel (app `backend/apps/agency`): the
PasarGuard admins (resellers), their limits, used / sold / hidden traffic, deleted-users accounting,
enforcement (disable an admin at 100 % of their limit, re-enable below it) and account groups.
Phase 1 = backend + data import; phase 2 = admin UI. Porting map: `backend/apps/agency/PORTING.md`.

## Admin UI (`/panel/agency`, permission `agency.view`)

Dashboard (Total Sold, Used, Remaining, Hidden, admins; the ≥80 % list) · Admins (search,
status / limit / group filters, usage bar, Total Sold, Sold Limit, Hidden, Remaining) · admin detail (every
PAMP number, user counts, snapshots, recent syncs, actions) · Groups · Accounting (`agency.accounting`) · Sync logs · Settings (sync,
enforcement, interval; `agency.manage`). Every number comes from the backend (`apps/agency/api.py` only
selects values computed by the ported code); the pages only format them.
Admin limits read in exact GB first ("5,200 GB", 1 GB = 1024³) with TB as the small secondary text; the
detail page section is "سقف ادمین / Admin limit".

**Cut-over gate** (open since 2026-10-16 — writes are live): while `agency_sync_enabled` is off, every write is off: set/remove limit, enable/disable admin or all their users, reset
deleted traffic, sync now and group edits answer `409 pre_cutover` and the buttons show "فعال پس از انتقال
نهایی". They open when `agency_sync_enabled` is turned on — which the Settings page only accepts after typing
`FINLAND-STOPPED` (that switch IS the cut-over). Enforcement can only be on while sync is on.

API: `GET /api/v1/admin/agency/` · `agency/admins/` · `agency/admins/<username>/` ·
`POST agency/admins/<username>/{set-limit|remove-limit|admin-action|reset-deleted-traffic}/` ·
`POST agency/sync-now/` · `GET/POST agency/groups/` + `PUT/DELETE agency/groups/<id>/` · `agency/sync-logs/` · `GET/PATCH agency/settings/` ·
`GET agency/portal-link/` + `agency/portal-link/qr.png` (portal address following the configured path; shown with
copy + QR in Agency Settings and on each admin's page).

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

## Cut-over — done 2026-10-16

Finland PAMP: celery + celery-beat stopped (web/db/nginx up, nothing deleted). This server syncs every 10 min with enforcement; the portal is open at `https://aicaspin.ir/agency/`.

**Rollback to Finland:** (1) here: Agency → Settings → turn off enforcement, sync and the portal — or `docker compose exec -T web python manage.py shell -c "from apps.settings_app.utils import set_setting; from apps.settings_app.models import ValueType; [set_setting(k, False, ValueType.BOOL) for k in ('agency_enforcement_enabled', 'agency_sync_enabled', 'agency_portal_enabled')]"`; (2) on Finland: `cd /opt/pamp && docker compose start celery celery-beat`. Never both on at once.

## Cut-over steps (reference)

1. Finland: stop `celery` + `celery-beat` (no more syncs).
2. Fresh dump → `import_pamp_dump … --replace`.
3. Turn on `agency_sync_enabled`, watch the first syncs, then `agency_enforcement_enabled`.

## Golden test

`./scripts/agency-golden.sh synthetic` regenerates the expectations by running the ORIGINAL PAMP v1.5.3
(its own image and a throw-away MySQL); `./scripts/test.sh apps/agency` compares the agency app with them.
`./scripts/agency-golden.sh real DUMP RESPONSES` does the same with real data (kept in
`backend/.golden_local/`, never committed).

## Reseller portal (`/agency/`, phase 3)

Resellers sign in with their **PasarGuard admin username and password**, checked against the panel's
`/api/admin/token` exactly like PAMP's `PanelAdminBackend`. They get their own 10-day session
(`Authorization: Agency <token>`, only a SHA-256 stored in `agency_reseller_session`, revoked on logout) —
never a customer JWT or staff token, and that token opens nothing but `/api/v1/agency/portal/`. Login is
throttled (`auth`, 10/min per IP) plus a per-username lockout after 5 failures (15 min).
A reseller sees PAMP's portal: their own numbers, block / 80 % warning states and support link; a group owner
sees the group's accounts (PAMP's account groups). Off until `agency_portal_enabled` (Settings → Reseller
portal) — until the cut-over its numbers are those of the last import.

## Accounting ledger (phase 4, permission `agency.accounting`)

Additive tables (`agency_admin_price`, `agency_ledger_entry`) — PAMP's numbers are only read.

* **Price per GB** (Toman) per admin with history; a price applies from its `valid_from` date on.
* **Quota charge (basis a)**: when a limit is raised through the agency panel (after the cut-over), a charge =
  increase in GB (1024³) × the price valid that day, rounded half-up to whole tomans. An unlimited admin counts
  as its **last finite limit** (0 only if it never had one), so re-limiting charges only the difference; lowering /
  removing a limit creates no credit; with no price set the grant is still recorded (amount 0, noted).
* Manual charges, signed adjustments, payments (card / cash / crypto / other); entries are never deleted —
  **voided** with a reason. Balance = charges + adjustments − payments.
* Statement per admin (Jalali dates, running balance), CSV export (UTF-8 BOM, Jalali dates), balance column in
  the admin list, overview tab "حسابداری". Resellers see their own statement read-only (no prices, no staff names).

## Limit history (Agency → admin → "Limit history", `agency.view`)

Table `agency_limit_change` (`apps/agency/limit_history.py`): **every** change of an admin's data limit, with the
old and new value (0 = unlimited), the action, who did it and from where, and the ledger entry it produced:

* **Agency panel** — create (with a limit), set / add / reduce, remove (unlimited): recorded with the staff user.
* **PasarGuard directly** — the sync compares the panel's limit with the stored one *before* overwriting it; a
  difference is recorded as *Changed in PasarGuard* (our own changes update the row at once, so they are not
  reported twice).
* **Baseline** — the value each admin had when the history started (v1.23.1).

Each record also writes an `agency.limit_changed` audit entry (`old_limit_bytes`, `new_limit_bytes`, GB/TB text,
`source`, `action`, `ledger_entry`). Units: GB = 1024³ bytes (PAMP's unit), TB = 1024⁴.

**Unlimited admins** (v1.23.2): `agency_panel_admin.last_limit_bytes` keeps the last *finite* limit (set by our
panel, admin creation and the sync; never cleared by "remove limit"). For an unlimited admin **Add / Reduce X**
start from it, and the quota charge of **Add** or **Set** is *new − last limit* (only an admin that never had a
limit is charged from 0). The confirm dialog shows both: "Unlimited now", the last limit used as the base, the new
limit and the GB × price that will be charged.

## Account groups (Agency → Groups, `agency.manage`)

PAMP's account groups, managed from the panel: create (optional name, owner = main admin, members, note),
edit (rename, change owner, add/remove members), delete (ConfirmDialog; accounts on the panel are untouched).
Storage stays PAMP's (`owner_username` unique + comma-separated `member_usernames`), plus a `name` column
(migration `agency.0003`, additive). Validation (`apps/agency/groups.py`): the owner and any NEW member must be
existing panel admins, the owner is never a member, duplicates are dropped, one group per owner; a member that
already left the panel may stay until removed. Each group shows its members (status, usage, Total Sold, Used,
users) and combined numbers (sums of the members' synced values). The portal reads the same rows, so a change
is what the owner sees on the next request (owner = group view; members and ex-owners = their own account).
Writes follow the cut-over gate and are audited (`agency.group_created|updated|deleted`).

## Group managers (Agency → Group managers / Approvals, v1.24.0; sign-in moved to /panel/ in v1.25.0)

Any number of **group managers**, each running one or more agency groups (nothing hard-coded: the
groups are the Account groups above). Since **v1.25.0** a manager signs in to the **main admin panel**
(`/panel/` login) as a staff account: `GroupManager.staff` → `Staff` with the RBAC role **Group manager**
(permission `agency.group_manager` only; never part of Super Admin) and the same username / password.
Existing managers were converted by migration `agency.0007` (same username + password hash; a username
already used by another staff account is never linked — the Managers page then says "no panel login").
The old portal is gone: `/agency/manager` forwards to the panel login, `POST agency/manager/login/`
answers **410**, an old `Manager <token>` header opens nothing.

**Server-side restriction (default-deny).** The *link* (not the role) restricts the staff:
`Staff.is_group_manager` → `StaffPermission` refuses **every** `/api/v1/admin/…` view (settings,
customers, orders, payments, transactions, tickets, CRM, agency, other groups — 403 for every method;
a test walks all admin routes) unless the view sets `group_manager_ok`, and `Staff.has_perm()` answers
false for everything except `agency.group_manager` (receipts, ticket files, live sockets stay closed
even if someone gives the account another role). The manager API `/api/v1/agency/manager/*` takes the
normal staff JWT and only a staff linked to an **active** manager (`IsGroupManagerStaff`); a superadmin
or other staff get 403 there. `GET admin/auth/me/` returns `group_manager {id, username}` and
`permissions: ["agency.group_manager"]`, so the panel draws the reduced menu.

**Staff page ↔ Group managers (v1.25.2).** Giving a staff account the **Group manager** role on
*Roles & staff* now makes it a group manager (`managers.sync_from_staff`): the existing link, else an
unlinked manager with the same username, else a new one (same password hash, **no groups**). The staff
modal shows **Assigned groups** — groups, allowed PasarGuard roles per group and the unapproved-volume
cap — the very record Agency → Group managers edits (same validation: owner roles refused, groups must
exist), so both pages always show the same thing. A manager without a group is flagged on both pages
(`warnings: ["no_group"]`, "no group" badge / warning). Removing the role (or making the staff a
superadmin) unlinks it: the manager is disabled and keeps its history (audit `agency.manager.unlinked`).
Agency → *New group manager* with the username of an existing staff that has the role links that account
(it keeps its own password) instead of refusing. Migration `agency.0008` linked the staff accounts that
already had the role (e.g. `imantorabian`) — without assigning any group.

**Panel menu for a manager** (`components/adminNav.js` → `GM_GROUPS`, page `pages/GroupManager.jsx`):
*Group admins* (`/my-groups`), *New admin* (`/my-groups/new`), *Accounting* (`/my-groups/accounting`,
incl. the group statement — the staff Agency `GroupStatement` component) and *Activity*
(`/my-groups/activity`). Every other route redirects to `/my-groups`. Disabling a manager or resetting
its password ends its panel sessions (`Staff.token_version`).

**Staff** (`agency.manage`; list with `agency.view`): create / edit / disable managers (the linked
staff account follows: created with the role, active flag, display name; a username taken by another
staff account is refused), reset the password (random, shown once; panel sessions end), assign groups and per group the **allowed inbounds**.
In PasarGuard 5.4 an admin's inbounds come from its **role** (`RoleAccess.allowed_group_ids`), so
"allowed inbounds" = allowed roles, shown with the inbound groups each opens; **owner roles are never
allowed**. Optional **max unapproved GB** (empty = no cap).

**Manager pages** (inside `/panel/`, fa/en, phone + desktop), only the admins of their groups:
usage, limit, users, status, remaining, inbounds, balance, pending GB —
* **new admin**: username, password, inbounds (allowed list), initial GB > 0 → created on PasarGuard
  at once (so it can make users right away) and added to the group;
* **add volume** (increase only): live limit read from PasarGuard, `+GB` applied at once; the
  confirm shows current → new;
* **password** and **inbounds** (allowed roles only) of their admins;
* **accounting** (read-only): per admin charges / payments / balance and statement, group total debt,
  pending (unapproved) volume apart, Jalali date filter, CSV / Excel; **group statement** (below);
* **activity**: their own actions and staff decisions.

**Never** (API-enforced, each answers 403, tested): reduce or remove a limit, unlimited (0 GB),
add volume to an unlimited admin, touch an owner/sudo admin, delete admins, roles outside the list,
payments, prices, other groups' admins / statements, any staff endpoint.

**Approvals** (Agency → Approvals, badge on the Agency menu + tab, in-site toast when new ones arrive,
polled every 30 s). Every create / add-volume is a `VolumeRequest` (*pending*): group, manager, admin,
GB, old → new limit, price × GB = amount (price valid on the request day).
* **Approve** (`agency.manage` + `agency.accounting`) → a `quota_charge` dated the request day, from the
  limit before → after (the v1.23.2 last-limit logic), linked to the limit-history row
  (source *Group manager*). An admin without a price for that day: the dialog asks for one (saved from
  that day). **Bulk approve** for many at once.
* **Reject** (`agency.manage`, confirm) → the GB are taken back on PasarGuard (live limit − GB, never 0 =
  unlimited; a rejected new admin keeps a 1-byte limit), a `reduce` row in the limit history, no charge.
* **Cap**: pending GB of a manager + new GB > cap → `409 cap_reached`, nothing sent to PasarGuard,
  until staff approve.

**Audit**: `agency.manager.*` (admin_created, volume_added, password_changed, inbounds_changed —
staff label `manager:<username>`, never a password), `agency.managers.*` (staff edits),
`agency.approval.approved|rejected`. Each group card on the Groups page has an **Activity** list.

## Group statement (Accounting → By group; manager → Accounting)

One combined statement per group: every charge, payment and adjustment of all its admins (admin name
per row, voided rows shown but not counted), running balance (opening balance before the range),
charges / payments of the range, closing balance, **group total debt**, and the pending (unapproved)
items listed apart (not in the balance). Jalali date filter, CSV / Excel (`?export=csv|xlsx`) and print.
Staff (`agency.accounting`) see any group: `GET agency/ledger/groups/` and
`agency/ledger/groups/<id>/statement/`; a manager only their own: `GET agency/manager/groups/<id>/statement/`.

### How to create a group manager

1. Agency → **Group managers** → **New group manager**.
2. Username, password (or **Random**), display name, optional max unapproved GB.
3. Tick the group(s) and, under each, the allowed inbound sets (roles).
4. **Create** → the card shows the sign-in address (the panel login, `https://<domain>/panel/login` or
   your panel path), username and password once — copy and send them. The manager signs in there and
   sees only the group-manager menu.
