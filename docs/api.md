# API overview

Base: `/api/v1/`. Full machine spec: `/api/schema/` — interactive: `/api/docs/`.

Three token audiences:
- **customer JWT** — `Authorization: Bearer <token>`, from `/api/v1/auth/login|register|telegram/miniapp`, refreshed at `auth/token/refresh`
- **staff JWT** — `Authorization: Bearer <token>`, from `/api/v1/admin/auth/login|refresh` (HS256, claim `type=staff_access`)
- **SMS device** — `X-Device-Token: <api_token>` (Android SMS Bridge app / iPhone shortcut)

WebSockets: `/ws/notifications/?token=<customer JWT>` (live site notifications) ·
`/ws/admin/payments/?token=<staff JWT>` (live payments queue + pending count).

## Public
- `GET /` · `GET /health/`
- `GET /config/` (branding, phone rule) · `GET /theme/` · `GET /pages/` · `GET /pages/{slug}/`
- `GET /plans/` (active plans)

## Customer auth (`/auth/`)
`register` (`terms_accepted: true` required — stored as `User.terms_accepted_at`) · `login` ·
`telegram/miniapp` (Telegram `initData` → JWT) · `token/refresh` · `logout` · `me` (GET/PATCH) ·
`password/change` · `password/reset` (+ `/confirm`) · `email/verify/resend` (+ `/confirm`) · `legacy/import`

## Customer app
- `GET /services/` · `GET /services/{id}/` · `GET /services/{id}/qr/` (PNG) ·
  `POST /services/{id}/refresh/` · `POST /services/{id}/revoke/` · `GET /services/{id}/renew-info/` · `POST /services/{id}/renew/`
- `POST /orders/` (new / renew / add-on; returns the reserved unique amount) · `GET /orders/` · `GET /orders/{id}/` ·
  `GET /orders/{id}/checkout/` (resume an open invoice — survives leaving the browser for the bank app)
- `GET /payments/cards/` · `POST /payments/receipt/` (multipart) · `GET /payments/{id}/receipt/` (owner or staff only)
- `GET /notifications/` · `POST /notifications/{id}/read/` · `POST /notifications/read-all/` · `GET /notifications/unread-count/`

## SMS device (Android app / iPhone shortcut, `X-Device-Token`)
- `POST /payments/sms/inbound/` `{text, sender?, received_at?}` → parse amount → auto-match an order
- `GET /payments/sms/ping/` (connection test, returns the device name)
- `GET /payments/sms/sources/` (allowed bank sender numbers the app filters on)

## Admin (`/api/v1/admin/`, staff JWT — each route needs a permission code)

| Area | Endpoints |
|---|---|
| auth | `auth/login` · `auth/refresh` · `auth/me` |
| dashboard / monitoring | `dashboard/` · `monitoring/` · `health/` · `resources/` · `backups/` (+ `run/`) · `system/` (version + update) · `telegram-stats/` |
| users | `users/` (CRUD, `stats/`, `{id}/orders/`, `{id}/set-password/`, `{id}/enable|disable/`, `legacy-import/`) · **`{id}/delete/`** `{reason}` — soft delete (perm `users.delete`) |
| deleted users | `deleted-users/?search=&from=&to=&state=deleted|restored` · `deleted-users/{id}/` (full snapshot + restore conflicts) · `deleted-users/{id}/restore/` (409 + conflicting fields) |
| services | `services/?filter=active|on_hold|disabled|expired|online&search=` · `services/{id}/` (PATCH: status, data_limit_gb, expire_date, on_hold_days, group_ids, note, **hwid_limit**) · `{id}/panel-detail/` · `{id}/status|reset|revoke/` · DELETE (perm `services.delete`) · `sync-now/` · POST `services/` (manual create) · **`panel-users/?panel=&search=`** (live panel search) · **`link/`** (adopt an existing panel account, `imported` order) |
| catalog | `plans/` · `cards/` (+ deposit report) · `panels/` (+ `{id}/test/`, `{id}/groups/`) · `pages/` · `themes/` (+ `{id}/activate/`) |
| finance | `payments/pending/` · `payments/{id}/approve|reject/` · `transactions/` (+ `{id}/status/`) · `accounting/` (period or Jalali `from`/`to`) |
| messaging | `notifications/` (+ `broadcast/`) · `channels/` (required channels) · `integrations/telegram/` · `bots/stats/` · `bots/backup-test/` · `integrations/email/` |
| settings | `settings/` (typed settings) · `branding/` · `integrations/panel/` (+ `test/`, `groups/`) · `sms-devices/` · `sms-sources/` |
| **apps** | `apps/` (Android SMS Bridge + iPhone shortcut info) · `apps/{android|ios}/` (POST multipart: file, version, link, notes, clear_file) · `apps/{android|ios}/download/` — served from this server (perm `settings.manage`) |
| RBAC | `roles/` · `permissions/` · `staff/` |
