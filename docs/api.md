# API overview

Base: `/api/v1/`. Full machine spec: `/api/schema/` — interactive: `/api/docs/`.

Token audiences:
- **customer JWT** — `Authorization: Bearer <token>`, from `/api/v1/auth/login|register|telegram/miniapp`, refreshed at `auth/token/refresh`, ended at `auth/logout` `{refresh}` (works with an expired access token)
- **staff JWT** — `Authorization: Bearer <token>`, from `/api/v1/admin/auth/login|refresh` (HS256, claim `type=staff_access`), revoked at `admin/auth/logout` `{refresh}`

Sign-in endpoints (login, register, refresh, logout, password reset, email confirm, Mini App, staff login/refresh/logout) ignore any `Authorization` header and cookies, answer `Cache-Control: no-store` and expire the old `sessionid` / `csrftoken` root cookies. The API authenticates by JWT only — no session / CSRF.
- **SMS device** — `X-Device-Token: <api_token>` (Android SMS Bridge app / iPhone shortcut)
- **reseller** — `Authorization: Agency <token>` from `/api/v1/agency/portal/login/` (PasarGuard admin credentials; only a
  SHA-256 stored); opens nothing but `/api/v1/agency/portal/`
- **Blu collector** — HMAC-SHA256 signature over the raw body (`POST /payments/blu/webhook/`, [blu-webhook.md](blu-webhook.md))

WebSockets: `/ws/notifications/?token=<customer JWT>` (live site notifications) ·
`/ws/admin/payments/?token=<staff JWT>` (live payments queue + pending count).

## Public
- `GET /` · `GET /health/`
- `GET /config/` (branding, phone rule) · `GET /theme/` · `GET /pages/` · `GET /pages/{slug}/`
- `GET /plans/` (active plans)
- `GET /domain-probe/{nonce}/` (domain wizard reachability probe) · `/.well-known/caspin/{token}` (store-domain check, answered before any host check) · `/api/v1/store-unavailable/` (v1.53.2: the 503 page of a store that is not active — parked hosts only)
- `POST /telegram/hook/{tenant_id}/` (v1.49: a store bot's Telegram webhook — secret header, our host only)
- `GET /exports/download/{tenant}/{token}/` (v1.53: a store backup, token-only, one use, only on the host the link was made for)

## Customer auth (`/auth/`)
`register` (`terms_accepted: true` required — stored as `User.terms_accepted_at`) · `login` ·
`telegram/miniapp` (Telegram `initData` → JWT) · `token/refresh` · `logout` · `me` (GET/PATCH) ·
`password/change` · `password/reset` (+ `/confirm`) · `email/verify/resend` (+ `/confirm`) · `legacy/import`

## Customer app
- `GET /services/` · `GET /services/{id}/` · `GET /services/{id}/qr/` (PNG) ·
  `POST /services/{id}/refresh/` · `POST /services/{id}/revoke/` · `GET /services/{id}/renew-info/` (`plan` own plan or null, `plans` renewal plans, `needs_plan`) · `POST /services/{id}/renew/` (`plan` optional: change / upgrade; required when the service has none). While a renewal is paid / under review: renew-info `can_renew: false` + `pending_renewal {state, plan_*, applies_by}`, renew / `orders/` / `orders/quote/` answer `code: renewal_waiting` (409; 400 on `orders/`); every service row carries `pending_renewal`
- `POST /orders/` (new / renew / add-on; optional `discount_code`; returns the reserved unique amount) · `POST /orders/quote/` (price + discount preview) · `GET /orders/` · `GET /orders/{id}/` · `POST /orders/{id}/account-name/` (a new name when the requested one is taken) ·
  `GET /orders/{id}/checkout/` (resume an open invoice — survives leaving the browser for the bank app) ·
  `GET /orders/credits/` (v1.56: my carried-over credits from a store import `{code, amount, expires_at}` — checkout offers them)
- WireGuard (v1.55, [wireguard.md](wireguard.md)): `GET /services/{id}/wireguard/` (locations: `key`, flag, names, `filename`; `all_filename`) · `GET /services/{id}/wireguard/{key|all}/` (the `.conf` / zip, straight from PasarGuard, never stored) · `POST /services/{id}/wireguard/{key|all}/send/` (Mini App: the bot sends the file to the customer's chat) — owner only, rate-limited, audited
- `GET /payments/cards/` · `POST /payments/receipt/` (multipart; optional `receipt_ref`) · `GET /payments/{id}/receipt/` (owner or staff only)
- Manual invoices (v1.38): `GET /orders/manual-invoices/` (my invoices + open count) · `POST /orders/manual-invoices/{id}/pay/` → normal checkout
- `GET /notifications/` · `POST /notifications/{id}/read/` · `POST /notifications/read-all/` · `GET /notifications/unread-count/` ·
  Web Push: `GET /notifications/push/` · `POST /notifications/push/subscribe|unsubscribe|test/`
- Tickets: `GET /tickets/topics/` (topics I may use + `has_active_service`) · `GET /tickets/?status=open|closed` ·
  `POST /tickets/` (multipart: `topic`, `subject`, `body`, `attachments[]` ≤ 3 × 5 MB JPEG/PNG/GIF/WebP/PDF, `service?`, `order?`;
  throttle `ticket` 60/h) · `GET /tickets/{id}/` (marks support replies read) · `POST /tickets/{id}/reply/` · `/close/` · `/reopen/` ·
  `GET /tickets/attachments/{id}/` (owner or scoped staff only)

## SMS device (Android app / iPhone shortcut, `X-Device-Token`)
- `POST /payments/sms/inbound/` `{text, sender?, received_at?}` → parse amount → auto-match an order
- `POST /payments/sms/inbound-batch/` — offline queue (iPhone Shortcut v1.1+): JSON array or NDJSON of
  `{text, sender, received_at}` (raw body or a multipart file). Idempotent (`sha256(device|received_at|text)`),
  matched at `received_at`; `received_at` > 5 min in the future or > 72 h old → refused (logged).
  → `{ok, result: "stored", count, new, duplicate, refused, matched, results: [{index, status, message_id, matched,
  order_id, reason, late}]}` — the Shortcut clears its queue only on `result == "stored"` ([sms-batch.md](sms-batch.md))
- `GET /payments/sms/ping/` (connection test, returns the device name)
- `GET /payments/sms/sources/` (allowed bank sender numbers the app filters on)

## Admin (`/api/v1/admin/`, staff JWT — each route needs a permission code)

| Area | Endpoints |
|---|---|
| auth | `auth/login` · `auth/refresh` · `auth/logout` · `auth/me` |
| dashboard / monitoring | `dashboard/` · `monitoring/` · `health/` · `resources/` · `backups/` (+ `run/`) · `system/` (version + update) · `telegram-stats/` |
| users | `users/` (CRUD, `stats/`, `{id}/orders/`, `{id}/set-password/`, `{id}/enable|disable/`, `legacy-import/`) · **`{id}/delete/`** `{reason}` — soft delete (perm `users.delete`) |
| deleted users | `deleted-users/?search=&from=&to=&state=deleted|restored` · `deleted-users/{id}/` (full snapshot + restore conflicts) · `deleted-users/{id}/restore/` (409 + conflicting fields) |
| services | `services/?filter=active|on_hold|disabled|expired|online&search=` · `services/{id}/` (PATCH: status, data_limit_gb, expire_date, on_hold_days, group_ids, note, **hwid_limit**) · `{id}/panel-detail/` · `{id}/status|reset|revoke/` · DELETE (perm `services.delete`) · `sync-now/` (runs now → `{checked, updated, errors, skipped, rows}`) · `{id}/sync/` · POST `services/` (manual create) · **`panel-users/?panel=&search=`** (live panel search) · **`link/`** (adopt an existing panel account, `imported` order; another panel admin's account → 409 `other_admin` unless `confirm_other_admin: true`). Manual create of a name that exists on the panel → 409 `exists_on_panel` |
| catalog | `plans/` · `cards/` (+ deposit report) · `panels/` (+ `{id}/test/`, `{id}/groups/`) · `pages/` · `themes/` (+ `{id}/activate/`) |
| finance | `payments/pending/` (rows carry `tx`, `invoice_amount`, `receipt_ref`, `receipt_amount`, `warnings`) · `payments/{id}/approve|reject/` · `payments/{id}/receipt-info/` (POST `receipt_amount` + `unit` rial/toman, `receipt_ref`) · `transactions/` (+ `{id}/status/`) · `accounting/` (period or Jalali `from`/`to`) |
| messaging | `notifications/` (+ `broadcast/`) · `channels/` (required channels) · `integrations/telegram/` · `bots/stats/` · `bots/backup-test/` · `email/` (SMTP relay settings, write-only password) · `email/test/` |
| settings | `settings/` (typed settings) · `branding/` (incl. `bot_support_*`, `qr_background`, multipart `qr_background_custom`; GET lists `qr_backgrounds`) · `branding/qr-preview/?bg=&size=` (PNG) · `integrations/panel/` (+ `test/`, `groups/`) · `sms-devices/` · `sms-sources/` |
| **apps** | `apps/` (Android SMS Bridge + iPhone shortcut info) · `apps/{android|ios}/` (POST multipart: file [android only — the iOS Shortcut is never uploaded], version, link, notes, clear_file) · `apps/{android|ios}/download/` — served from this server (perm `settings.manage`); **ios** is built from `mobile_shortcut/CaspinSMS.shortcut` with this server's endpoint, `?device=<id>` also injects that device's token (needs `sms.manage`) |
| RBAC | `roles/` · `permissions/` · `staff/` |
| docs | `docs/` (list) · `docs/{slug}/` (markdown, secrets masked) — perm `settings.manage` |
| SMS log | `sms-log/?matched=0` or `1` (masked text + reason) — perm `payment.view` |
| **tickets** | `tickets/?status=active|<s,s>&topic=&priority=&assigned=me|none|<id>&q=&source=&offset=` (inbox, `status_counts`, `badge`) · `tickets/badge/` · `tickets/{id}/` (messages incl. internal notes + events) · `{id}/reply/` (multipart, `internal`) · `{id}/assign/` · `{id}/assignable/` · `{id}/status/` · `{id}/priority/` — perms `tickets.view|reply|assign|close`, always within the staff topic scope · `tickets/topics/` (+ `{id}/`) · `tickets/settings/` · `tickets/staff-scopes/` (+ `{id}/`) — `tickets.manage_topics` · `tickets/telegram-link/` (GET / POST code / DELETE — any staff, for themselves). WebSocket `/ws/admin/tickets/?token=` (events + badge) |
| finance (v1.25+) | `transactions/` (`?status&method&source&manual=1&search&from&to` — Tehran days on the payment date; `?deleted=1` Super Admin; `?export=csv`) · `transactions/summary/` (cards: today / Jalali month from the list's own query, v1.38.3) · `transactions/{id}/delete-preview|delete|restore/` · `transactions/bulk-delete|bulk-restore/` · `transactions/{id}/undo-rounded/` (Super Admin) · `payments/blu-transactions/` (+ `{id}/attach/`) · `accounting/` |
| manual invoices (v1.38) | `users/{id}/manual-invoices/` (GET list `payment.view`; POST `mode=paid` multipart / `mode=issued` — `payments.manual_invoice`) · `users/{id}/manual-invoices/options/` · `manual-invoices/{id}/cancel/` |
| deleted users (v1.31.2+) | `deleted-users/{id}/purge/` · `deleted-users/bulk-purge/` · `deleted-users/purge-preview/` · `deleted-users/auto-purge/` (settings) — Super Admin + `users.purge` |
| CRM (v1.19+) | `crm/customers/{id}/` (360) · `/timeline/` · `/notes/` · `/cases/` · `/message/` · `/templates/{tpl}/preview/` · `crm/cases/` (+ `{id}/`, `close/`, `message/`, `ticket/`, `discount/`) · `crm/leads/` · `crm/reasons/` · `crm/tags/` · `crm/templates/` · `crm/staff/` · `crm/settings/` · `crm/reports/` · `crm/analytics/{overview|financial|retention|tickets}/` (read-only) · retention: `crm/warning-rules/` (+ `{id}/`) · `crm/retention/settings/` · `crm/retention/report/` |
| discount codes (v1.26) | `discounts/` (+ `{id}/`, `{id}/report/`) · `discounts/summary/` · `discounts/options/` · `discounts/customers/` |
| agency (staff) | `agency/` (overview) · `agency/admins/` (+ `{username}/`, `{username}/{action}/` — set-limit etc., `set-limit/preview/`, `limit-history/`) · `agency/panel-admins/` (+ `options/`, `{username}/` — PasarGuard admin CRUD) · `agency/groups/` (+ `{id}/`, `activity/`, `debt/`) · `agency/managers/` (+ `{id}/`, `password/`, `options/`) · `agency/approvals/` (+ `badge/`, `{id}/{approve|reject}/`, `bulk-approve/`) · `agency/ledger/…` (statements, entries void, group statements, monthly reports, CSV) · `agency/invoices/` (+ `settlement/`, `{id}/void/`, `{id}/settle-outside/`) · `agency/payments/` (+ `badge/`, `{id}/receipt/`, `{id}/{approve|reject}/`) · `agency/portal-access/{username}/` · `agency/portal-link/` (+ `qr.png`) · `agency/settings/` · `agency/sync-logs/` · `agency/sync-now/` — perms `agency.view|manage|accounting|payments` |
| domain / paths / access | `domain/` · `domain/settings/` · `domain/token/` (+ `test/`) · `domain/start/` · `domain/{id}/{step}/` · `domain/rollback/` · `domain/access/` (+ `settings/`, `detect/`, `dns01/`, `back/`) · `paths/` — Super Admin / `settings.manage` ([domain.md](domain.md), [access-mode.md](access-mode.md), [paths.md](paths.md)) |
| WireGuard (v1.55) | `wireguard/locations/` (+ `{id}/`) — «مکان‌های وایرگارد» (code, names, flag, file name, order) · `wireguard/template/` (GET / PUT the file-name template, validated as a tunnel name) — GET `plans.manage`, write `settings.manage` · plans carry `vpn_type` (`sub` / `wireguard` / `both`, checked against WireGuard groups) |
| failed orders (v1.42.1+) | `transactions/provision-failed/` · `transactions/{id}/retry-provision/` (optional new account name — same paid order, never a new charge) · store panel: `orders/provision-failed/` (+ `{id}/retry/`) |
| Blu linking (v1.42.2) | `payments/blu-transactions/{id}/candidates/` · `{id}/attach/` · `{id}/unlink/` (Super Admin, link-only rows) |
| misc | `cards/deposit-report/` · `channels/enforcement/` (forced join / phone switches) · `channels/{id}/test/` · `sms-devices/{id}/token/` · `tickets/canned/` (+ `{id}/`) · `tickets/staff/` · `agency/ledger/{username}/export.csv` · `plans/store-options/` (store plan editor: allowed panel groups of the reseller's role) |
| agency accounting (v1.58) | `agency/ledger/?period=month|prev|d7|custom&from=&to=&tab=debtors|all&group=&q=&sort=username|group|sales|paid|debt|last_payment|open_invoices&dir=asc|desc&page=&page_size=` → `{summary {sales, paid, debt, debtors, credit, adjust_*}, results (sales, paid, debt, last_payment, open_invoices, open_amount, group), count, page, pages, groups, from, to}` · `agency/ledger/<u>/?recent=5` (the drawer: last N entries + `entries_total`) · every report / statement / history carries `sales` (= charges + adjustments) + `adjust_count` / `adjust_down` / `adjust_up` (`net_sales` = old name of `sales`) |
| agency payments (v1.59) | rows carry `actions` (approve · reject · late_approve), `superseded_by`, `late_deposit`; `payments/{id}/approve/` `{late: true}` = «تأیید با تأخیر» (expired + a later exact deposit only) · status `superseded` |
| store domains (v1.60) | each domain row carries `steps` (dns · cert · nginx · health · active → state done / current / error / failed / waiting, `at`, `since`, `error` — empty for the store's own view), `stage`, `stage_since`; the store row adds `unreachable_because` (`store_inactive`, `no_active_domain`) |
| store theme (v1.60) | `agency/panel-admins/<u>/store/theme/` GET / PUT `{theme: <id> \| null}` (our staff, `agency.view` / `agency.manage`): null = follow our active theme; `themes/` is ours only (403 on a store) |
| SMS setup code (v1.60) | `sms-devices/<id>/setup-code/` (`sms.manage`, store_ok) → `{code, server, device}`; code = `SMS1:` + base64url(JSON `{u, t}`) without padding; `apps/` on a store = white-label (`whitelabel`, iPhone `endpoint` + `guide`, no iCloud / file), `apps/ios/download/` 404 there, `apps/android/download/` only a `sms-confirm*.apk` build, served as `sms-confirm.apk` |
| store services (v1.60) | `services/` answers on a store (its own services, `panel_name` blank): GET `services.view`; sync / status / edit / revoke `services.manage`; POST (manual create under the reseller, quota → 409 `quota`) `services.create`; `panel-users/` (reseller-owned only, PasarGuard `admin=`) + `link/` (another admin's → 403 `not_reseller`, linked elsewhere → 409 `linked_elsewhere`) `services.link`; reset / delete / `group_ids` refused there; `users/<id>/manual-invoices/…` store_ok (`payments.manual_invoice`) |
| CRM per store (v1.59) | every `crm/…` and `crm/analytics/…` endpoint answers on a store's domain with its data (codes `crm.view` / `crm.manage` / `crm.analytics`, opt-in); our panel adds `?store=<id>`; `crm/stores/` lists the stores; `crm/settings/` and `crm/retention/settings/` stay ours |
| SSL (v1.57) | `monitoring/ssl/` — GET the certificates (state, issuer, expiry, days left, sources, notes) · POST «بررسی الان» (202, `monitoring.view`, 409 while one runs) |
| agency history + archive (v1.54) | `agency/history/?scope=all|group|admin&group=&admin=&period=d7|month|prev|custom&from=&to=&export=csv|xlsx` (`agency.accounting`, archived admins included) · `agency/admins/?archived=1` (archived admins; restored automatically when back on PasarGuard) · group manager `agency/manager/history/` · portal `agency/portal/history/` |
| **stores — our side** (v1.43+, `agency.manage` unless noted; never on a store's domain) | `agency/panel-admins/{u}/store/` (GET / POST open / PATCH name, status, export switch, `requests_per_minute`) · `…/store/domains/` (+ `{id}/`, `{id}/check/`) · `…/store/bot/` (+ `check/` — token write-only) · `…/store/ceiling/` · `…/store/owner/` (password returned once) · `…/store/failed-orders/` (+ `{id}/retry/`) · `…/store/exports/` (+ `{id}/link/`) · `…/store/fee/` (`agency.accounting` to change) · `…/store/imports/` (v1.56: multipart upload → scan; + `{id}/` GET preview / DELETE discard, `{id}/run/` `{old_bot_stopped: true, plan_map, confirm_credits, credit_days}`, `{id}/undo/`, `{id}/report.csv`) — [multi-tenant.md](multi-tenant.md), [store-import.md](store-import.md) |
| **store mode** (on a store's own domain) | only views with `store_ok` answer (users, plans, payments queue + SMS + cards + devices, tickets, discounts, pages, themes, branding, settings — `TENANT_KEYS` only, roles / staff within the ceiling, dashboard); platform paths are 404 there. Store-only: `store-export/` (+ `{id}/link/`, perm `store.export` + our switch) |
| me / push | `auth/me/prefs/` (sound, volume, v1.57 `nav_open` = the sidebar sections open / closed) · `push/` · `push/subscribe|unsubscribe|test/` (Web Push for this staff member) · `staff/group-manager-options/` |

## Group manager (`/api/v1/agency/manager/`, staff JWT of a staff linked to a group manager — `agency.gm.*`)

`me/` (`?lite=1`) · `admins/` (`?q&sort&group&page&page_size`, POST = create) · `admins/live/` · `admins/{u}/stats/` · `admins/{u}/statement/` ·
`admins/{u}/{add-volume|password|role|enable|disable|profile|users}/` · `accounting/` · `groups/{id}/statement/` · `activity/` · `requests/` ·
`debt/` · `invoices/` (+ `settlement/`) · `payments/` (+ `all/` = «پرداخت کل بدهی», `{id}/`, `{id}/{receipt|cancel}/`) · `notices/` (`?page=`, POST `{id}` / `{read:true}`) ·
`prefs/` · `push/` (+ `{action}/`) · `password/`. Anything else → explicit 403.

## Reseller portal (`/api/v1/agency/portal/`, `Authorization: Agency <token>`)

`login/` · `logout/` · `me/` · `statement/?admin=` · `requests/` (+ `quote/?gb=`) · `invoices/` (+ `settlement/`) · `debt/` · `payments/`
(POST `{invoice_id}` or `{invoice_ids:[…]}`; `all/` = «پرداخت کل بدهی» `{expected_total}` → 409 `total_changed`; `{id}/`, `{id}/{receipt|cancel}/`) ·
`notices/` (`?page=`, POST `{id}` / `{read:true}`) · `push/` (+ `subscribe|unsubscribe|test/`). Read-only sub-admins get 403 on billing routes; a
blocked group owner cannot sign in ([agency.md](agency.md#access-rules-v135)).

