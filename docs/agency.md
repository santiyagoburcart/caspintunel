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

Finland PAMP: celery + celery-beat stopped (web/db/nginx up, nothing deleted). This server syncs every `agency_sync_interval_minutes` (production: 2 min since 2026-11) with enforcement; the portal is open at `https://caspintunel.com/agency/`.

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

**v1.38.2 layout.** The portal has sections with a menu (desktop sidebar, phone ☰ drawer): «داشبورد» (usage tiles with
(i) explanations), «درخواست شارژ», «درخواست‌های من», «فاکتورها و پرداخت», «صورت‌حساب», «اعلان‌ها», «تنظیمات» (language,
theme, notification sound, browser push), and a red «خروج» with a confirm at the bottom of the menu. A read-only sub-admin
sees only the dashboard, notifications and settings. Notices are in the header bell + notifications page
(`components/AgencyBell.jsx`, the same file as the group-manager bell; `portal/notices/` pages 20 at a time and marks one or
all read). «فاکتورها و پرداخت» = «کل بدهی» (open invoice remainders + old balance, `portal/debt/`) with «پرداخت کل بدهی»
(`portal/payments/all/` → `billing.pay_all(None, …, admin=…)`, one payment and one unique amount, 409 `total_changed`), a
collapsed «پرداخت انتخابی» (several invoices / the old balance via `portal/invoices/settlement/`), the invoice list with its
own «پرداخت», and the payment history. Each invoice shows its source (`invoice_source`: «درخواست ادمین» / «مدیر گروه» /
«شارژ دستی» / «تسویه مانده قبلی»). Browser push for resellers: `portal/push/…`, rows with `push_subscription.reseller`,
sent by `billing.notice(admin=…)`. An open portal tab checks every 5 minutes (and on focus) whether index.html points to a
new bundle and offers «بارگذاری دوباره».

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

**After a limit change (v1.52.2, incident farzin3 2026-11-10)**:
* **Block released at once** (`release.py::release_if_room`): every limit change through our panel — set / add / remove,
  an approved charge request, a group manager's add — ends an enforcement block (`pamp_blocked`) right away when the admin is
  now unlimited or below its limit: `enable_admin` on PasarGuard, flag cleared, audit `agency.enforcement_released`
  (`…_release_failed` + the next sync retries when PasarGuard refuses; the limit change itself never fails). PAMP's
  enforcement stays verbatim — it only checks admins WITH a limit, so before this an admin made unlimited kept a stale
  «محدود‌شده» label.
* **Dialog warnings**: the new limit leaves < 5 % of it or < 50 GB above current usage → «تقریباً بلافاصله دوباره محدود
  می‌شود» (`actions.low_headroom`); an unlimited admin that never had a limit → «کل X گیگ شارژ می‌شود» with the amount and the
  volume already used (`full_charge`).
* **Daily summary** (`near_limit.py`, beat «agency: near-limit summary», 10:00 Tehran, created once by seed — staff may move or
  switch it off): admins ≥ 95 % of their limit with % / GB left / state, a silent Telegram message to our staff with
  `agency.manage`; nothing when none, skipped while the sync is off.

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

**Group names (v1.25.3).** A group's name (Agency → Groups → edit; blank = shown by its owner) is
shown everywhere a group appears: admins list chips and filter, admin detail, group managers,
the staff page, approvals and activity (resolved live by group id, so renaming also relabels old rows),
ledger group statements. Production: #2 "Vox" (owner VEX2), #3 "Mostafa" (owner Mostafa-ho).

**Admin role picker (v1.27.1).** Managers choose **نقش ادمین (Role)**: the PasarGuard admin roles read
live (`/api/admin-roles/simple` via `roles_catalog`, cached 60 s), shown by **name only**. Owner (sudo)
roles never. If staff chose allowed roles for the group, only those; if none were chosen, every
non-owner role (`managers.allowed_roles`). The manager UI and API never mention inbounds: roles are
`{id, name}`, the action is `POST manager/admins/<u>/role/`, the audit row is `agency.manager.role_changed`
(old activity rows are shown as such, without inbounds). Staff pages still show the inbounds per role.

**Group-manager abilities as permissions (v1.27).** Each ability is its own permission on the Roles
page, section *Agency – group manager* (Persian names): `agency.gm.view_admins` (group admins),
`create_admin` (incl. profile title + support link, also editing them later), `add_volume`,
`toggle_admin` (enable / disable), `admin_password`, `admin_role`, `view_users` (an admin's users,
read-only), `accounting` (accounting + statements + group statement), `activity`. A role is a
group-manager role when it holds `agency.group_manager`; the "Group manager" role gets every ability
when created (migration `agency.0009` gave the existing role all of them once — the seed never
resets an operator's choice). Groups stay assigned per user. Every manager API checks its permission
(403 `{"permission": …}`), `auth/me` lists them, and the menu, tabs and buttons follow; `me/` returns
no admin rows without `view_admins`. Super Admin never holds these codes (they restrict).

**Manager tools (v1.27).** Enable / disable an admin of its own groups (with confirm; an admin the
limit enforcement blocked stays with staff), audited `agency.manager.admin_enabled|admin_disabled`
and shown in Activity. Users of an admin, read-only (`GET manager/admins/<u>/users/` → PasarGuard
`/api/users?admin=<u>`: username, status, used / limit, expiry, online / last seen; search, status,
20 per page; rows of another admin are dropped). Support link + profile title on create and in the
admin's Settings (`GET/POST manager/admins/<u>/profile/`, read from PasarGuard, audited with the
change). Create-admin shows the allowed **roles** — a group picker only when the manager has several groups.
Admin search on Group admins, Accounting and the group statement (shared with staff).

**Admin passwords (v1.27).** PasarGuard refuses weak admin passwords, so staff and managers use one
rule, checked before anything reaches PasarGuard (`admin_crud.password_problem`, panel
`lib/adminPassword.js`): 12+ characters, 2+ upper-case, 2+ lower-case, 2+ digits, one of
`# . $ @ ! % & * - _ + = ?`, no spaces / non-ASCII, not containing the username. "Random password"
always satisfies it; a weak one gets `code: weak_password` with the rule in Persian (`detail_fa`).

**Panel menu for a manager** (`components/adminNav.js` → `GM_GROUPS`, page `pages/GroupManager.jsx`):
*Group admins* (`/my-groups`), *New admin* (`/my-groups/new`), *Accounting* (`/my-groups/accounting`,
incl. the group statement — the staff Agency `GroupStatement` component) and *Activity*
(`/my-groups/activity`). Every other route redirects to `/my-groups`. Since v1.25.5 a manager has its own **Settings** tab (`/my-groups/settings`, last bottom tab on phones, avatar in the header → Settings): profile (username, role, assigned groups with allowed inbounds, cap), **change own password** (`POST agency/manager/password/` — needs the current password, ends other sessions, returns fresh tokens for this one, keeps `GroupManager.password` in step), language, light/dark and logout. The sidebar/drawer account block of other staff is not shown to managers.

**Statement notes in Persian (v1.25.5).** Notes the server writes (no price, approved request #N, pending approval, limit-history notes, …) are stored in English and returned with `note_fa` (`apps/agency/notes.py`); the panel shows it in Persian and the fa CSV/Excel exports use it. Notes typed by people are shown as typed. On phones the group statement shows each row as a card. Disabling a manager or resetting
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


## Group managers page (v1.28)

Agency → Group managers shows one card per manager: status, last sign-in, created (and by whom);
**Groups**; **Roles allowed for new admins** (PasarGuard role names as chips per group — "All roles
(except owner)" when staff picked none); **Permissions** (the nine `agency.gm.*` abilities of the
manager's panel role, ticked / struck through, with a link to Roles & permissions); **Unapproved
volume cap** (pending of cap, bar, pending requests). The edit form picks roles as chips (names
only). The list API adds `panel_role`, `permissions[{code,en,fa,on}]` and `assignments[].all_roles`.


## Invoices and payments (v1.34)

- **Invoices** (Agency → Accounting → «فاکتورها», admin page → Accounting): every charge — staff limit raise, manual
  charge (with GB: GB × price), approved group-manager volume, approved admin request — issues `INV-000123` =
  GB × the admin's price per GB of that day. No price → the action is refused with «قیمت هر گیگ برای این ادمین
  تعریف نشده» and staff with `agency.accounting` get a Telegram (admin + GB); set the price, then retry.
  Statuses: unpaid → pending (receipt / near-miss deposit under review) → paid; voided (staff, unpaid only — voids
  the charge too). Balances from before invoices: one «تسویه مانده قبلی» invoice per admin (admin page → Accounting).
- **Admin requests** (`/agency/` → «درخواست شارژ»): GB + optional note, price preview. They appear in Agency →
  Approvals marked «درخواست ادمین» (who asked, group, note) and on Telegram with Approve / Reject. Only staff with
  agency.manage + agency.accounting approve (never a group manager): the limit goes up on PasarGuard at once (from
  the last finite limit), charge + invoice. A rejection reason is shown to the admin.
- **Paying**: the admin pays one invoice in the portal; a group manager (`agency.gm.invoices`) selects several of its
  groups' unpaid invoices at `/panel/my-groups/invoices` for one payment. Checkout: card, unique amount (shared pool
  with customer orders), timer, optional receipt. SMS / Blu deposits confirm it like a customer order (exact amount in
  the window; ±20 % → review; rounded-amount rule with a receipt or a known payer card; duplicates refused). Staff
  review the rest in Agency → Accounting → «واریزهای نمایندگان» (`agency.payments`). Approval: invoices paid, a
  payment entry per admin in the ledger (a rounded shortfall stays owed), the payer notified in the portal / panel.
- Agency payments never appear in customer Transactions, Accounting revenue, Analytics or the customer queue; Blu
  deposits that paid one are labelled «واریز نماینده» on the Blu tab.
- Invoice kinds: `quota_charge` (limit raised), `manual_charge`, `request` (approved admin request), `settlement`
  («تسویه مانده قبلی») and, since v1.53, `store_fee` — a reseller store's monthly fee («اشتراک فروشگاه», `tenancy/fees.py`,
  off by default), issued through the ledger like any charge and paid the same way.

## Invoices and the ledger (v1.35.1)

Invoices are settled by **allocation rows** (`agency_invoice_allocation`, `apps/agency/allocation.py`), not by a status flip:
- **«ثبت پرداخت»** (admin page → Accounting): staff choose which unpaid invoices it settles, or leave «خودکار (قدیمی‌ترین اول)».
  Partial is allowed — the invoice shows paid / remaining and stays «پرداخت جزئی»; fully covered → «پرداخت‌شده (دستی)».
  Money beyond the chosen / open invoices lowers the older (not invoiced) balance.
- **«اصلاحیه · کاهش بدهی»**: settle selected invoices, oldest first (default) or none → «تسویه با اصلاحیه».
  **«افزایش بدهی» never touches invoices.**
- **«تسویه خارج از سیستم»** (invoice action, `agency.accounting`): for money received outside (e.g. older months). The invoice
  is settled, its charge is NOT voided, the ledger balance does not change, and it is no longer offered as «مانده قبلی».
  **«باطل کردن»** is different: it removes the invoice AND its charge (the confirm dialog says so).
- An agency checkout (portal / group manager) settles its invoices the same way («پرداخت‌شده»); a partly paid invoice
  asks only for the rest.
- **Invariant**: an admin's open invoice remainder never exceeds its ledger debt (max(0, balance)). After every ledger
  entry, void and new invoice, `allocation.enforce` settles the excess oldest first, attributed to payments / decreases
  since the first invoice that still have unallocated credit (e.g. a payment recorded just before the charge), else
  «تسویه با مانده حساب». Voiding a payment / adjustment re-opens what it settled. The admin page warns when the two
  differ («ناهماهنگی …»).
- Old data: `manage.py reconcile_agency_invoices` previews per admin (read-only); `--apply` writes the same plan (audited).

## Group debt page (v1.35.2, `/panel/my-groups/invoices`)

- **«کل بدهی گروه»** (`billing.debt_breakdown`, `GET /agency/manager/debt/`): live from the ledger — every group admin's open
  invoice remainders + its old balance not invoiced yet (balance − open invoices − settled outside). Without outside settlements
  it equals Σ max(0, ledger balance). Items already in a payment under review are shown but not payable.
- **«پرداخت کل بدهی»** (`billing.pay_all`, `POST /agency/manager/payments/all/ {expected_total}`): issues the settlement invoices for
  old balances and bundles every unpaid item into ONE payment with one unique amount → the normal checkout (card, timer, receipt,
  SMS / Blu auto-confirm). If the total changed since the page loaded → 409 `total_changed` + the new total (nothing created);
  the page shows the new amount and asks again. Only admins whose invoices the manager pays (`payer_for`).
- **«ریز بدهی»**: read-only, collapsible per admin (invoice number, GB, amount, date; old balance as one line); zero-debt admins
  hidden unless «نمایش همه». «پرداخت انتخابی (پیشرفته)» stays collapsed at the bottom; payments are in «سابقه پرداخت‌ها».
- A new «تسویه مانده قبلی» invoice is allowed whenever an un-invoiced balance remains and none is open (debt added after a paid one).
- Staff: Agency → Groups → each group shows the same «کل بدهی گروه» (`GET /admin/agency/groups/<id>/debt/`, agency.accounting).

## Group-manager panel layout (v1.37)

- **«ادمین‌های گروه»**: `GET /agency/manager/admins/?q=&sort=name|usage|debt&group=&page=&page_size=` — searched over ALL of
  the manager's admins on the server, 20 per page; group chips filter; «+ ادمین جدید» opens a compact dialog (the separate
  «ادمین جدید» page / nav entry is gone, `/my-groups/new` redirects). `GET manager/me/?lite=1` skips the admin rows.
- **Notifications**: header bell with the unread count + dropdown (phones: bottom sheet) and `/my-groups/notifications`
  (`GET manager/notices/?page=` 20 each, `POST {id}` one read / `{read: true}` all); no notices block inside pages. Each new
  notice also goes to the manager's browsers (Web Push, `billing.notice`).
- **«حسابداری»**: one compact filter bar (period chips, from / to, admin search, CSV / Excel), debt / pending tiles, admin list
  20 / 50 / 100 per page.
- **Settings**: profile, password, language / theme, and «اعلان‌ها» (sound + volume — `manager/prefs/`, same `Staff.notify_prefs`;
  browser push — `manager/push/`, `subscribe|unsubscribe|test`). Since v1.38.1 the header avatar only opens Settings (no dropdown); «خروج» is a red button at the bottom of the sidebar (desktop) and at the bottom of the Settings tab (phones), always behind a confirm (`components/LogoutButton.jsx`).
- **«فعالیت‌ها»**: `GET manager/activity/?type=&admin=&page=` — types create / volume / status / password / role / profile /
  payment / request / sign-in (colour + icon each); includes the manager's own payments and volume requests.

## Approvals on Telegram and bulk approve (v1.33)

A new approval (group-manager volume or an admin's «درخواست شارژ») is sent by `agency/notify.py::approval_requested` to staff
with `agency.manage` (DM after Telegram linking, backup chat as fallback) with **Approve / Reject** buttons
(`ag:*` callbacks, `handle_callback`). The same checks as the panel apply (`managers.approve` / `managers.reject`, the staff
member's permissions; a price that has to be set first asks for confirmation). A cap reached or an admin changed by a
group manager is also posted. In the panel, **Approvals** can approve several rows at once
(`POST /admin/agency/approvals/bulk-approve/ {ids}`, ≤ 200, `agency.manage` + `agency.accounting`); each row is approved on
its own (one failure does not stop the rest; the answer lists `approved` and `failed`).

## Group-manager admin cards (v1.38.1)

Compact card per admin: name · status · role, usage bar with %, cap / used / remaining in one row, debt, user chips (total /
active / online / expired / limited). Actions: «افزودن حجم» · «کاربران» · «جزئیات» + «⋯» (change password, change role,
settings, disable / enable — a pamp-blocked admin shows why it cannot be enabled). The full numbers live only in
«جزئیات» (with the (i) explanations). The grid sizes columns by the list's own width; a short last row spans the free width.
Every group-manager list uses the same compact centred pager.

## Full reseller stats for group managers (v1.36)

Permission **«مدیر گروه: مشاهده آمار کامل نمایندگان»** (`agency.gm.full_stats`, granted to every group-manager role by
migration `agency.0013`, narrowed on the Roles page). With it, «ادمین‌های گروه» cards and the «جزئیات» dialog show what the
staff Agency page shows — sold (Σ user caps), used, remaining, sell limit left (remaining − sold + used), hidden traffic
(sold − used − remaining), deleted users' traffic, usage % — from the SAME code (`api.admin_row` / `enrich._enrich`, no new
formulas), each with a Persian (i) explanation. Live from PasarGuard (read-only, cached 60 s, `manager_views.live_stats`):
users by status (`/api/system/users?admin_username=`), online now, last activity (newest `online_at`). Endpoints:
`GET /agency/manager/admins/live/?u=…` (≤ 60 per call), `GET /agency/manager/admins/<username>/stats/`. Own groups only;
without the permission these keys are removed server-side.

## Profile title / support link are header-safe (v1.35.3)

PasarGuard puts an admin's `support_url` into every subscription response **raw** (`support-url:` header; `profile-title` is
base64). An invisible character pasted from Telegram (U+2060 WORD JOINER after the link, incident 2026-11-03, Mostafa-ho)
made the header invalid and Happ showed "400 Bad Request" until the field was re-saved in PasarGuard. Every save from our
panel (staff Settings tab, group manager «تنظیمات», create) now goes through `admin_crud.clean_field`: titles NFC, one line,
no control / zero-width / direction marks (ZWNJ kept for Persian); links plain ASCII http(s) (IDN host → punycode,
`@name` / `t.me/name` → `https://t.me/name`, user:password@ refused). `manage.py check_admin_profiles [--apply]` lists
(and re-saves) admins with unsafe values on PasarGuard; values that are merely not a link are only reported.

## Access rules (v1.35)

- **Who pays an admin's invoices — one place only** (`billing.payer_for`): the group manager when the admin's group has
  an active group manager, otherwise the admin itself in `/agency/`. `create_payment` refuses the other side (403).
- **`/agency/` sign-in** (`billing.portal_access`, checked at login AND on every request):
  owner of a group with a manager → blocked, «لطفاً از پنل مدیریت گروه وارد شوید» + a link to `/panel/`;
  sub-admin of such a group → read-only (own usage only; one line says the account is with the manager);
  no manager → unchanged (request «درخواست شارژ برای: <admin>», invoices, pay).
  Per-admin override on the staff admin page (Accounting tab → «ورود به پرتال نمایندگان»): rule / allowed (read-only if
  managed) / blocked — `AgencyAdminSetting`, `PUT /admin/agency/portal-access/<username>/` (agency.manage).
- **Group managers** (`/panel/my-groups/invoices`, «فاکتورها و پرداخت»): group total unpaid, every admin's balance and its
  old (not invoiced) balance with «پرداخت مانده قبلی» (issues the settlement invoice, then pays it), invoices (empty state),
  multi-invoice payment, and — with `agency.gm.request_volume` — «درخواست شارژ» for any admin of their groups: same
  Approvals queue / Telegram buttons as admin requests; approval raises that admin's limit and issues its invoice.

## Archive instead of delete (v1.54)

An agency admin is **never deleted** on our side. When it disappears from PasarGuard (the 2-minute sync) or our staff delete
it (Agency → admin → Settings → delete), it is **archived** («حذف‌شده», `archived_at`, reason `panel_missing` / `deleted`,
`agency/archive.py`):

- hidden from the active admin list, the sync loop, enforcement, the dashboard numbers and the group-manager admin list
  (`PanelAdmin.objects` — the default manager — skips archived rows; `PanelAdmin.all_objects` sees them);
- **kept**: ledger, invoices, payments, allocations, prices, limit history, usage snapshots, `AdminLimit`, volume requests,
  notices, its group membership (a group it owns stays);
- shown under **«بایگانی»** (Agency → Admins, and the group manager's admin list), its page opens with a banner; actions that
  would touch PasarGuard answer 409 `archived`; its balance can still be paid / adjusted, and it stays in the group's debt
  and «پرداخت کل بدهی»;
- the same username back on PasarGuard (or created again in our panel) **restores** the row — history continues.

The sync's delete is the one deliberate deviation from PAMP's verbatim code (see `PORTING.md`); `tests/test_golden.py` still
matches PAMP v1.5.3 for every stored value.

Deleting a **group manager's** staff account deactivates + archives the manager instead (`archived_at`): its requests,
payments, notices and activity stay; its groups pay directly again (`billing.manager_of_group` counts active managers only).
Agency → Group managers has its own «بایگانی» list.

## «تاریخچه» — history that never resets (v1.54)

`agency/history.py`, from immutable records only (the ledger — mistakes are voided, never edited — the invoices and
`AgencyUserSeen`): for the last 7 days, the current Jalali month, the last Jalali month or a custom range, and a 12-month
table — volume sold (GB on quota + manual charges), «شارژ ناخالص» (gross charges), «اصلاحیه‌ها» (adjustments, signed),
**«فروش»** (v1.57, the one sales / income figure) = charges + adjustments — a «کاهش بدهی» lowers it, an «افزایش بدهی» raises
it, in the period it is recorded (an adjustment corrects a mistake, e.g. a wrong charge); invoiced, paid, opening / closing
balance, new users (first seen by the sync; counted from v1.54). The gross charges are never shown — not in the KPIs, tables,
statements, manager views, portal or any CSV / Excel. **«اصلاحیه‌ها»** appear only as a separate information line (count +
debt decreases + debt increases), never as a column, and in the ledger each adjustment is its own row type «اصلاحیه».

| Who | Where | Scope |
|---|---|---|
| our staff (`agency.accounting`) | Agency → حسابداری → «تاریخچه»; admin → حسابداری | all agency · a group · an admin (archived ones included) |
| group manager (`agency.gm.accounting`) | حسابداری tab | its groups' admins + group totals |
| the admin | /agency/ portal → «تاریخچه» (full access) | its own account |

Each view exports CSV / Excel (period totals, per admin, 12 months).

## Reseller stores (multi-tenant, v1.43+)

An agency admin can get a white-label store (own domain, bot, Mini App, plans, cards, staff) — opened and managed by our staff
on Agency → admin → «فروشگاه» (`agency.manage`). The store sells from the admin's own PasarGuard quota (`tenancy/quota.py` reads
the agency numbers — never a separate formula), its services are created under the admin (`set_owner`), and our agency
invoicing per GB is unchanged. The same card holds the store's domains, bot, staff ceiling + owner login, failed orders,
backups, the monthly fee (`agency.accounting`) and «ورود داده از ربات قبلی» (v1.56, [store-import.md](store-import.md)).
Design and status: [multi-tenant.md](multi-tenant.md); pilot checklist: [pilot-fa.md](pilot-fa.md).

## Accounting page (v1.58) and colours (v1.57)

- **Agency → «حسابداری»** (`agency/accounting.py`, API `agency/ledger/`): a period selector (this month · last month · 7 days ·
  custom) and a summary strip — «فروش», «پرداخت‌شده» (period), «جمع بدهی» (what admins owe now), «تعداد بدهکارها», with
  «اصلاحیه‌ها» as an information line only. Tabs: **«بدهکارها»** (default: owes, or has an open invoice) · **«همه نماینده‌ها»** ·
  **«واریزهای نمایندگان»** (the review queue) · **«تاریخچه ۱۲ ماهه»**; group statements and invoices are links in the same bar.
- **One table**: admin · group · sales (period) · paid (period) · debt · last payment · open invoices (count + still owed) ·
  «ثبت پرداخت» / «صورت‌حساب». Filter by group and search (admin or group name), sort by any column, 25 / 50 / 100 per page —
  every choice in the URL. A row opens a **side drawer**: a short summary + the last 5 ledger entries
  (`agency/ledger/<u>/?recent=5`) + «ثبت پرداخت» + «صفحهٔ کامل ادمین» — the full ledger lives only on the admin page. The old
  KPIs, chart and «جزئیات ماه به تفکیک نماینده» list were removed (their numbers are the table's columns); the export endpoints stay.
- The **group manager's «حسابداری»** has the same layout: period + strip, tabs «بدهکارها» · «همهٔ ادمین‌ها» · «صورت‌حساب گروه» ·
  «تاریخچه ۱۲ ماهه», one sortable table, a drawer with the last 5 entries, CSV / Excel and the full statement on demand.
  Its rows carry `debt` (now) next to `balance` (at the range end) and `open_amount`.
- **Colours** (`lib/agencyTone.js` + `agency-tones.css`, identical in both SPAs, light + dark, contrast-safe `--c-*-fg` text):
  active green · limited amber · disabled / blocked red · archived grey; usage bars < 70 % green, 70–90 % amber, > 90 % red;
  debt red · credit green · zero neutral; invoices unpaid red / under review amber / paid green / voided grey; requests and
  payments waiting amber / approved green / rejected red; «اصلاحیه» purple; KPI tiles tinted in their accent.

