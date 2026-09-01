# API overview

Base: `/api/v1/`. Full machine spec: `/api/schema/` — interactive: `/api/docs/`.

Three token audiences, all `Authorization: Bearer <token>`:
- **customer JWT** — `/api/v1/auth/login|token/refresh`
- **staff JWT** — `/api/v1/admin/auth/login|refresh` (HS256, claim `type=staff_access`)
- **SMS device** — `X-Device-Token: <api_token>` (Android app only)

## Public
- `GET /` · `GET /health/`
- `GET /config/` · `GET /theme/` · `GET /pages/` · `GET /pages/{slug}/`
- `GET /plans/` (active plans)

## Customer (`/auth/`, JWT)
`register` · `login` · `token/refresh` · `logout` · `me` (GET/PATCH) ·
`password/change` · `password/reset` (+ `/confirm`) · `email/verify/resend` (+ `/confirm`)

## Customer app
- `GET /services/` · `GET /services/{id}/` · `GET /services/{id}/qr/` (PNG)
- `POST /orders/` (create → returns `payment_instructions`) · `GET /orders/` · `GET /orders/{id}/`
- `GET /payments/cards/` · `POST /payments/receipt/` (multipart)

## SMS app
- `POST /payments/sms/inbound/` `{text, sender?, received_at?}` → auto-match
- `GET /payments/sms/ping/`

## Admin (`/api/v1/admin/`, staff JWT — each route needs a permission code)
`auth/{login,refresh,me}` · `dashboard` · `users/` (+ `set-password`, `enable`, `disable`, `legacy-import`) ·
`plans/` · `cards/` (+ `deposit-report/`) · `transactions/` · `accounting/` (period or Jalali `from`/`to`) ·
`notifications/` (broadcast) · `branding/` · `services/?filter=expired|on_hold|online` ·
`telegram-stats/` · `health/` · `resources/` · `backups/` (+ `run/`) · `system/` (version + update) ·
`roles/` · `permissions/` · `staff/` · `pages/` · `themes/` (+ `{id}/activate/`)
